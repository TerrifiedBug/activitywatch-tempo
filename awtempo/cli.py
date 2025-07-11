#!/usr/bin/env python3
"""
ActivityWatch to Jira Tempo Automation Script
Command-line interface for the modular ActivityWatch Tempo system
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .automation_manager import AutomationManager
from .config_manager import update_config_files, ConfigurationError

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="ActivityWatch to Jira Tempo automation script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate daily preview for yesterday
  aw-tempo

  # Generate weekly preview for last week
  aw-tempo --weekly

  # Generate preview for specific date
  aw-tempo --date 2024-01-15

  # Submit preview entries to Tempo
  aw-tempo --submit

  # Direct submission (legacy mode)
  aw-tempo --direct

  # Start scheduler
  aw-tempo --scheduler

  # Test connections
  aw-tempo --test-connections

  # Update configuration files
  aw-tempo --update-config
        """
    )

    parser.add_argument(
        '--preview',
        action='store_true',
        help='Generate preview file for manual review (default action)'
    )

    parser.add_argument(
        '--submit',
        action='store_true',
        help='Submit entries from preview file to Tempo'
    )

    parser.add_argument(
        '--direct',
        action='store_true',
        help='Process and submit directly without preview (legacy mode)'
    )

    parser.add_argument(
        '--weekly',
        action='store_true',
        help='Process weekly data (Monday-Friday)'
    )

    parser.add_argument(
        '--date',
        type=str,
        help='Specific date to process (YYYY-MM-DD format)'
    )

    parser.add_argument(
        '--scheduler',
        action='store_true',
        help='Start the automated scheduler'
    )

    parser.add_argument(
        '--test-connections',
        action='store_true',
        help='Test connections to ActivityWatch and Jira'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.json',
        help='Configuration file path (default: config.json)'
    )

    parser.add_argument(
        '--update-config',
        action='store_true',
        help='Merge new default settings into your configuration files'
    )

    return parser.parse_args()


def validate_date(date_str: str) -> datetime:
    """Validate and parse date string"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD")
        sys.exit(1)


def main():
    """Main entry point"""
    args = parse_arguments()

    # Handle configuration updates first
    if args.update_config or not Path(args.config).exists():
        try:
            update_config_files(args.config)
            if args.update_config:
                logger.info("Configuration files updated successfully")
                return
        except Exception as e:
            logger.error(f"Failed to update configuration files: {e}")
            sys.exit(1)

    # Initialize automation manager
    try:
        manager = AutomationManager(args.config)
    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        logger.error("Please run 'aw-tempo --update-config' to create configuration files")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Handle test connections
    if args.test_connections:
        success = manager.test_connections()
        sys.exit(0 if success else 1)

    # Parse date if provided
    target_date = None
    if args.date:
        target_date = validate_date(args.date)

    # Determine processing mode
    mode = "weekly" if args.weekly else "daily"

    # Execute based on arguments
    try:
        if args.preview:
            logger.info("Generating preview file...")
            manager.generate_preview(mode, target_date)

        elif args.submit:
            logger.info("Submitting entries from preview file...")
            success = manager.submit_preview_entries()
            if not success:
                sys.exit(1)

        elif args.direct:
            logger.info("Direct processing mode (no preview)...")
            if target_date:
                if mode == "weekly":
                    # Process the week containing the target date
                    days_since_monday = target_date.weekday()
                    start_date = target_date - timedelta(days=days_since_monday)
                    entries = manager.process_weekly_activities(start_date)
                    if entries:
                        manager.jira_integration.submit_daily_entries(entries)
                else:
                    manager.process_specific_date(target_date)
            else:
                manager.process_yesterday()

        elif args.scheduler:
            logger.info("Starting scheduler...")
            manager.start_scheduler()

        else:
            # Default behavior - always use preview mode
            logger.info("Generating preview file...")
            manager.generate_preview(manager.config.default_processing_mode, target_date)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
