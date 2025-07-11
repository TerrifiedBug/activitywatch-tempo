"""
Main automation manager for ActivityWatch Tempo
"""

import json
import logging
import schedule
import time
from datetime import datetime, timedelta
from typing import List, Optional

from .models import Config, TimeEntry, StaticTask
from .config_manager import (
    load_config, setup_logging, load_window_mappings, load_static_tasks,
    ConfigurationError
)
from .activity_watch import ActivityWatchProcessor, ActivityWatchError
from .jira_tempo import JiraTempoIntegration, JiraTempoError
from .time_processor import TimeProcessor

logger = logging.getLogger(__name__)


class AutomationManager:
    """Main automation manager that coordinates all components"""

    def __init__(self, config_file: str = "config.json"):
        try:
            self.config = load_config(config_file)
            setup_logging(self.config)
            
            self.window_mappings = load_window_mappings(self.config.mappings_file)
            self.static_tasks = load_static_tasks(self.config.static_tasks_file)
            
            self.processor = ActivityWatchProcessor(self.config, self.window_mappings)
            self.jira_integration = JiraTempoIntegration(self.config)
            self.time_processor = TimeProcessor(self.config)
            
            logger.info("AutomationManager initialized successfully")
            
        except ConfigurationError as e:
            logger.error(f"Configuration error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AutomationManager: {e}")
            raise

    def process_yesterday(self):
        """Process yesterday's activities"""
        yesterday = datetime.now() - timedelta(days=1)
        self.process_specific_date(yesterday)

    def process_specific_date(self, date: datetime):
        """Process activities for a specific date"""
        logger.info(f"Processing activities for {date.strftime('%Y-%m-%d')}")
        
        try:
            # Get static tasks for this date
            static_tasks = self._get_static_tasks_for_date(date)
            
            # Process ActivityWatch data
            entries = self.processor.process_daily_activities(date, static_tasks)
            
            if not entries:
                logger.info("No time entries found for the specified date")
                return
            
            # Process time entries (rounding and sequential allocation)
            entries = self.time_processor.process_time_entries(entries, date)
            
            # Submit to Jira Tempo
            success = self.jira_integration.submit_daily_entries(entries)
            
            if success:
                logger.info(f"Successfully processed and submitted {len(entries)} time entries")
            else:
                logger.error("Failed to submit some time entries")
                
        except ActivityWatchError as e:
            logger.error(f"ActivityWatch error: {e}")
        except JiraTempoError as e:
            logger.error(f"Jira Tempo error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error processing date {date}: {e}")

    def process_weekly_activities(self, start_date: datetime) -> List[TimeEntry]:
        """Process a week's activities (Monday to Friday)"""
        logger.info(f"Processing weekly activities starting {start_date.strftime('%Y-%m-%d')}")
        
        all_entries = []
        
        # Process each day of the week
        for i in range(5):  # Monday to Friday
            current_date = start_date + timedelta(days=i)
            
            try:
                # Get static tasks for this date
                static_tasks = self._get_static_tasks_for_date(current_date)
                
                # Process ActivityWatch data
                daily_entries = self.processor.process_daily_activities(current_date, static_tasks)
                
                if daily_entries:
                    # Process time entries
                    daily_entries = self.time_processor.process_time_entries(daily_entries, current_date)
                    all_entries.extend(daily_entries)
                    
            except Exception as e:
                logger.error(f"Error processing {current_date.strftime('%Y-%m-%d')}: {e}")
                continue
        
        logger.info(f"Processed {len(all_entries)} total entries for the week")
        return all_entries

    def _get_static_tasks_for_date(self, date: datetime) -> List[StaticTask]:
        """Get static tasks that should be applied for a specific date"""
        day_name = date.strftime('%A').lower()
        applicable_tasks = []
        
        for task in self.static_tasks:
            if not task.enabled:
                continue
                
            # Check if this task should be added for this date
            if task.day_of_week is None:  # Daily task
                applicable_tasks.append(task)
            elif task.day_of_week == day_name:  # Weekly task on specific day
                applicable_tasks.append(task)
        
        return applicable_tasks

    def create_preview_file(self, entries: List[TimeEntry], start_date: datetime, end_date: datetime, mode: str):
        """Create a preview file for manual review"""
        preview_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": end_date.strftime('%Y-%m-%d'),
                "mode": mode,
                "total_entries": len(entries),
                "total_hours": sum(e.duration_seconds for e in entries) / 3600
            },
            "entries": []
        }
        
        # Sort entries by start time
        sorted_entries = sorted(entries, key=lambda e: e.start_time)
        
        for entry in sorted_entries:
            entry_data = {
                "jira_key": entry.jira_key,
                "start_time": entry.start_time.strftime('%Y-%m-%dT%H:%M:%S'),
                "duration_seconds": entry.duration_seconds,
                "duration_hours": entry.duration_seconds / 3600,
                "description": entry.description,
                "is_static_task": entry.is_static_task
            }
            preview_data["entries"].append(entry_data)
        
        # Write to file
        with open(self.config.preview_file_path, 'w') as f:
            json.dump(preview_data, f, indent=2)
        
        logger.info(f"Created preview file: {self.config.preview_file_path}")
        logger.info(f"Total: {len(entries)} entries, {preview_data['metadata']['total_hours']:.2f} hours")

    def load_preview_file(self) -> List[TimeEntry]:
        """Load entries from preview file"""
        try:
            with open(self.config.preview_file_path, 'r') as f:
                preview_data = json.load(f)
            
            entries = []
            for entry_data in preview_data.get('entries', []):
                entry = TimeEntry(
                    jira_key=entry_data['jira_key'],
                    duration_seconds=entry_data['duration_seconds'],
                    start_time=datetime.fromisoformat(entry_data['start_time']),
                    description=entry_data['description'],
                    is_static_task=entry_data.get('is_static_task', False)
                )
                entries.append(entry)
            
            logger.info(f"Loaded {len(entries)} entries from preview file")
            return entries
            
        except FileNotFoundError:
            logger.error(f"Preview file not found: {self.config.preview_file_path}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in preview file: {e}")
            return []
        except Exception as e:
            logger.error(f"Error loading preview file: {e}")
            return []

    def submit_preview_entries(self) -> bool:
        """Submit entries from preview file to Jira Tempo"""
        entries = self.load_preview_file()
        
        if not entries:
            logger.error("No entries to submit from preview file")
            return False
        
        logger.info(f"Submitting {len(entries)} entries from preview file")
        
        try:
            success = self.jira_integration.submit_daily_entries(entries)
            
            if success:
                logger.info("Successfully submitted all entries from preview file")
                # Optionally backup the preview file
                import shutil
                backup_path = f"{self.config.preview_file_path}.backup"
                shutil.copy2(self.config.preview_file_path, backup_path)
                logger.info(f"Backed up preview file to {backup_path}")
            else:
                logger.error("Failed to submit some entries from preview file")
            
            return success
            
        except Exception as e:
            logger.error(f"Error submitting preview entries: {e}")
            return False

    def generate_preview(self, mode: Optional[str] = None, date: Optional[datetime] = None):
        """Generate preview file for manual review"""
        if mode is None:
            mode = self.config.default_processing_mode

        if date is None:
            if mode == "weekly":
                # Default to previous week (Monday to Friday)
                today = datetime.now()
                days_since_monday = today.weekday()
                last_monday = today - timedelta(days=days_since_monday + 7)
                start_date = last_monday
                end_date = last_monday + timedelta(days=4)  # Friday
            else:
                # Default to yesterday
                start_date = end_date = datetime.now() - timedelta(days=1)
        else:
            if mode == "weekly":
                # If specific date provided for weekly, use that week
                days_since_monday = date.weekday()
                start_date = date - timedelta(days=days_since_monday)
                end_date = start_date + timedelta(days=4)  # Friday
            else:
                start_date = end_date = date

        logger.info(f"Generating {mode} preview for {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        try:
            if mode == "weekly":
                entries = self.process_weekly_activities(start_date)
            else:
                static_tasks = self._get_static_tasks_for_date(start_date)
                entries = self.processor.process_daily_activities(start_date, static_tasks)
                if entries:
                    entries = self.time_processor.process_time_entries(entries, start_date)

            if entries:
                self.create_preview_file(entries, start_date, end_date, mode)
            else:
                logger.info(f"No time entries found for the specified {mode} period")

        except Exception as e:
            logger.error(f"Error generating preview: {e}")

    def start_scheduler(self):
        """Start the automated scheduler"""
        logger.info("Starting automated scheduler")
        
        # Schedule daily processing at 8 AM
        schedule.every().day.at("08:00").do(self.process_yesterday)

        logger.info("Scheduler started. Daily processing at 8:00 AM")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}")

    def test_connections(self) -> bool:
        """Test connections to ActivityWatch and Jira"""
        logger.info("Testing connections...")
        
        # Test ActivityWatch connection
        try:
            self.processor._get_window_bucket()
            logger.info("✓ ActivityWatch connection successful")
        except ActivityWatchError as e:
            logger.error(f"✗ ActivityWatch connection failed: {e}")
            return False
        
        # Test Jira Tempo connection
        try:
            if self.jira_integration.test_connection():
                logger.info("✓ Jira Tempo connection successful")
            else:
                logger.error("✗ Jira Tempo connection failed")
                return False
        except Exception as e:
            logger.error(f"✗ Jira Tempo connection failed: {e}")
            return False
        
        logger.info("All connections successful!")
        return True 