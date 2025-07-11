"""
ActivityWatch integration for time tracking
"""

import logging
import re
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .models import Config, TimeEntry, WindowMapping, StaticTask

logger = logging.getLogger(__name__)


class ActivityWatchError(Exception):
    """Raised when there's an issue with ActivityWatch integration"""
    pass


class ActivityWatchProcessor:
    """Processes ActivityWatch data for Jira integration"""

    def __init__(self, config: Config, window_mappings: List[WindowMapping] = None):
        self.config = config
        self.aw_client_url = "http://localhost:5600"
        self.window_mappings = window_mappings or []
        self._bucket_cache = None

    def _get_window_bucket(self) -> Optional[str]:
        """Get the window watcher bucket name with caching"""
        if self._bucket_cache is not None:
            return self._bucket_cache

        try:
            response = requests.get(f"{self.aw_client_url}/api/0/buckets", timeout=10)
            response.raise_for_status()
            buckets = response.json()

            window_bucket = None
            for bucket_name in buckets.keys():
                if 'window' in bucket_name:
                    window_bucket = bucket_name
                    break

            if not window_bucket:
                raise ActivityWatchError("No window watcher bucket found in ActivityWatch")

            self._bucket_cache = window_bucket
            logger.info(f"Found ActivityWatch window bucket: {window_bucket}")
            return window_bucket

        except requests.exceptions.RequestException as e:
            raise ActivityWatchError(f"Failed to connect to ActivityWatch: {e}")
        except Exception as e:
            raise ActivityWatchError(f"Error getting ActivityWatch buckets: {e}")

    def get_activity_data(self, date: datetime) -> List[Dict]:
        """Fetch ActivityWatch data for a specific date with proper timezone handling"""
        try:
            window_bucket = self._get_window_bucket()
            
            # Create timezone-aware datetime objects
            # Assume local timezone if not specified
            local_tz = ZoneInfo("local")
            start_time = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=local_tz)
            end_time = start_time + timedelta(days=1)

            query_params = {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            }

            logger.debug(f"Querying ActivityWatch events from {start_time} to {end_time}")

            response = requests.get(
                f"{self.aw_client_url}/api/0/buckets/{window_bucket}/events",
                params=query_params,
                timeout=30
            )
            response.raise_for_status()

            events = response.json()
            logger.info(f"Retrieved {len(events)} ActivityWatch events")
            return events

        except requests.exceptions.RequestException as e:
            raise ActivityWatchError(f"Failed to fetch ActivityWatch data: {e}")
        except Exception as e:
            raise ActivityWatchError(f"Error processing ActivityWatch data: {e}")

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp with proper timezone handling"""
        try:
            # Remove 'Z' and add timezone info if not present
            if timestamp_str.endswith('Z'):
                timestamp_str = timestamp_str[:-1] + '+00:00'
            
            # Parse the timestamp
            dt = datetime.fromisoformat(timestamp_str)
            
            # Convert to local timezone if it's UTC
            if dt.tzinfo == ZoneInfo("UTC"):
                local_tz = ZoneInfo("local")
                dt = dt.astimezone(local_tz)
            
            return dt
        except Exception as e:
            logger.error(f"Error parsing timestamp '{timestamp_str}': {e}")
            # Fallback to current time
            return datetime.now()

    def check_window_mappings(self, window_title: str, app_name: str) -> Optional[Tuple[str, str]]:
        """Check if window title matches any configured mappings"""
        for mapping in self.window_mappings:
            if not mapping.enabled:
                continue

            # Use case-insensitive matching by default
            flags = re.IGNORECASE
            match_found = False

            # Check based on match_type
            if mapping.match_type == "title":
                match_found = re.search(mapping.pattern, window_title, flags) is not None
            elif mapping.match_type == "app":
                match_found = re.search(mapping.pattern, app_name, flags) is not None
            else:  # "both" or default
                match_found = (re.search(mapping.pattern, window_title, flags) is not None or
                             re.search(mapping.pattern, app_name, flags) is not None)

            if match_found:
                logger.info(f"[MATCH] Mapping matched: '{mapping.name}' -> {mapping.jira_key} (match_type: {mapping.match_type})")
                return (mapping.jira_key, mapping.description)
            else:
                logger.debug(f"[NO MATCH] Pattern '{mapping.pattern}' (match_type: {mapping.match_type}) did not match title: '{window_title}' or app: '{app_name}'")

        logger.debug(f"[SEARCH] No mappings matched for: '{window_title}' (app: '{app_name}')")
        return None

    def extract_jira_tickets(self, window_title: str, app_name: str) -> Optional[str]:
        """Extract Jira ticket IDs from window titles or app names"""
        # Look for SE- pattern in window titles using the configured pattern
        jira_pattern = self.config.jira_ticket_pattern

        matches = re.findall(jira_pattern, window_title, re.IGNORECASE)
        if matches:
            return matches[0].upper()

        # Check if it's a Teams meeting with Jira ID
        if 'teams' in app_name.lower() and 'SE-' in window_title:
            matches = re.findall(jira_pattern, window_title, re.IGNORECASE)
            if matches:
                return matches[0].upper()

        return None

    def categorize_activity(self, window_title: str, app_name: str) -> str:
        """Categorize activity type based on application and window title"""
        app_lower = app_name.lower()
        title_lower = window_title.lower()

        if 'teams' in app_lower or 'zoom' in app_lower or 'meet' in app_lower:
            if 'standup' in title_lower or 'daily' in title_lower:
                return "Standup"
            return "Meeting"

        if any(ide in app_lower for ide in ['code', 'studio', 'intellij', 'pycharm']):
            return "Development"

        if 'jira' in title_lower or 'atlassian' in title_lower:
            return "Task Management"

        if any(browser in app_lower for browser in ['chrome', 'firefox', 'edge']):
            if any(dev_site in title_lower for dev_site in ['stackoverflow', 'github', 'docs']):
                return "Research"
            return "General"

        return "General"

    def process_daily_activities(self, date: datetime, static_tasks: List[StaticTask] = None) -> List[TimeEntry]:
        """Process a day's activities into time entries with comprehensive error handling"""
        try:
            events = self.get_activity_data(date)
        except ActivityWatchError as e:
            logger.error(f"Failed to get ActivityWatch data: {e}")
            return []

        time_entries = []
        activity_blocks = {}  # Group by jira key

        # Add static tasks for this date
        if static_tasks:
            static_entries = self._create_static_task_entries(static_tasks, date)
            time_entries.extend(static_entries)

        if not events:
            logger.info("No ActivityWatch events found for the specified date")
            return time_entries

        # Process ActivityWatch events
        logger.info(f"[PROCESSING] Processing {len(events)} ActivityWatch events for grouping")
        processed_count = 0
        skipped_count = 0

        for event in events:
            try:
                window_title = event.get('data', {}).get('title', '')
                app_name = event.get('data', {}).get('app', '')
                duration = event.get('duration', 0)
                timestamp_str = event.get('timestamp', '')

                # Skip events with missing data
                if not window_title or not app_name or not timestamp_str:
                    logger.debug(f"[SKIP] Skipping event with missing data: {event}")
                    skipped_count += 1
                    continue

                timestamp = self.parse_timestamp(timestamp_str)

                logger.debug(f"[EVENT] Processing event: '{window_title}' (app: '{app_name}', duration: {duration}s)")

                # Determine jira_key and activity details
                jira_key = None
                mapped_description = None

                # Check for window mappings first
                mapping_result = self.check_window_mappings(window_title, app_name)
                if mapping_result:
                    jira_key, mapped_description = mapping_result
                    logger.debug(f"[MAPPED] Mapped to: {jira_key} via window mapping")
                    processed_count += 1
                else:
                    # Try to extract Jira ticket from title
                    jira_key = self.extract_jira_tickets(window_title, app_name)
                    if jira_key:
                        logger.debug(f"[TICKET] Found Jira ticket: {jira_key}")
                        processed_count += 1
                    else:
                        logger.debug(f"[SKIP] No Jira ticket or mapping found, skipping: '{window_title}'")
                        skipped_count += 1
                        continue

                # Group activities by jira_key
                if jira_key not in activity_blocks:
                    activity_blocks[jira_key] = {
                        'total_duration': 0,
                        'activities': [],
                        'mapped_description': mapped_description
                    }
                    logger.debug(f"[NEW] Created new activity block for: {jira_key}")

                # Add this event to the activity block
                activity_blocks[jira_key]['total_duration'] += duration
                activity_blocks[jira_key]['activities'].append({
                    'timestamp': timestamp,
                    'duration': duration,
                    'title': window_title,
                    'app': app_name
                })
                logger.debug(f"[ADD] Added {duration}s to {jira_key} (total: {activity_blocks[jira_key]['total_duration']}s, events: {len(activity_blocks[jira_key]['activities'])})")

            except Exception as e:
                logger.error(f"Error processing event {event}: {e}")
                skipped_count += 1
                continue

        # Convert activity blocks to time entries
        logger.info(f"[CONVERT] Converting {len(activity_blocks)} activity blocks to time entries")
        for jira_key, block in activity_blocks.items():
            try:
                total_duration = block['total_duration']
                activity_count = len(block['activities'])

                if total_duration < self.config.minimum_activity_duration_seconds:
                    logger.debug(f"[SKIP] Skipping short activity block {jira_key}: {total_duration}s (< {self.config.minimum_activity_duration_seconds}s)")
                    continue

                # Use mapped description if available, otherwise create generic description
                if block['mapped_description']:
                    description = block['mapped_description']
                else:
                    description = f"Work on {jira_key}"
                    if activity_count > 1:
                        description += f" ({activity_count} activities)"

                entry = TimeEntry(
                    jira_key=jira_key,
                    duration_seconds=total_duration,
                    start_time=min(act['timestamp'] for act in block['activities']),
                    description=description,
                    is_static_task=False,
                    original_timestamp=min(act['timestamp'] for act in block['activities'])
                )
                time_entries.append(entry)

                # Log the grouped entry
                hours = total_duration / 3600
                logger.info(f"[ENTRY] Created time entry: {jira_key} - {hours:.2f}h ({activity_count} activities grouped)")

            except Exception as e:
                logger.error(f"Error creating time entry for {jira_key}: {e}")
                continue

        # Log processing summary
        logger.info(f"[SUMMARY] Processed {processed_count} events, skipped {skipped_count} events")
        logger.info(f"[RESULT] Created {len(time_entries)} time entries from {len(activity_blocks)} activity blocks")

        return time_entries

    def _create_static_task_entries(self, static_tasks: List[StaticTask], date: datetime) -> List[TimeEntry]:
        """Create time entries for static tasks"""
        static_entries = []
        day_name = date.strftime('%A').lower()

        for task in static_tasks:
            if not task.enabled:
                continue

            should_add = False

            # Check if this task should be added for this date
            if task.day_of_week is None:  # Daily task
                should_add = True
            elif task.day_of_week == day_name:  # Weekly task on specific day
                should_add = True

            if should_add:
                try:
                    # Parse time
                    time_parts = task.time.split(':')
                    task_time = datetime.time(int(time_parts[0]), int(time_parts[1]))

                    entry = TimeEntry(
                        jira_key=task.jira_key,
                        duration_seconds=task.duration_minutes * 60,
                        start_time=datetime.combine(date.date(), task_time),
                        description=task.description,
                        is_static_task=True,
                        original_timestamp=datetime.combine(date.date(), task_time)
                    )
                    static_entries.append(entry)
                    logger.info(f"Added static task: {task.name} ({task.duration_minutes}min)")
                except Exception as e:
                    logger.error(f"Error creating static task entry for {task.name}: {e}")

        return static_entries

    def round_time_duration(self, duration_seconds: int) -> int:
        """Round time duration UP to the next configured interval"""
        rounding_seconds = self.config.time_rounding_minutes * 60

        # Round UP to next interval (ceiling)
        import math
        rounded_seconds = math.ceil(duration_seconds / rounding_seconds) * rounding_seconds

        # Ensure minimum duration (don't round to 0)
        if rounded_seconds == 0 and duration_seconds > 0:
            rounded_seconds = rounding_seconds

        return rounded_seconds

    def validate_daily_hours(self, entries: List[TimeEntry]) -> List[TimeEntry]:
        """Check daily hours and warn if over limit (no automatic scaling)"""
        total_seconds = sum(entry.duration_seconds for entry in entries)
        max_seconds = self.config.working_hours_per_day * 3600

        if total_seconds > max_seconds:
            excess_hours = (total_seconds - max_seconds) / 3600
            logger.warning(f"Total time ({total_seconds/3600:.1f}h) exceeds daily limit ({self.config.working_hours_per_day}h) by {excess_hours:.1f}h")
            logger.warning("Manual adjustment required in preview file before submission")

            # Show which items can't fit in the daily limit
            self._log_overflow_items(entries, max_seconds)

        return entries  # Return unchanged - no automatic scaling

    def _log_overflow_items(self, entries: List[TimeEntry], max_seconds: int):
        """Log specific items that exceed the daily limit"""
        # Sort entries by duration (largest first) to show what could be reduced
        sorted_entries = sorted(entries, key=lambda e: e.duration_seconds, reverse=True)

        running_total = 0
        items_that_fit = []
        items_that_dont_fit = []

        for entry in sorted_entries:
            if running_total + entry.duration_seconds <= max_seconds:
                items_that_fit.append(entry)
                running_total += entry.duration_seconds
            else:
                items_that_dont_fit.append(entry)

        logger.warning(f"Items that fit in daily limit ({max_seconds/3600:.1f}h):")
        for entry in items_that_fit:
            logger.warning(f"  - {entry.jira_key}: {entry.duration_seconds/3600:.2f}h")

        logger.warning(f"Items that exceed daily limit:")
        for entry in items_that_dont_fit:
            logger.warning(f"  - {entry.jira_key}: {entry.duration_seconds/3600:.2f}h")

        # Suggest reductions
        suggestions = self._suggest_reductions(items_that_dont_fit, max_seconds - running_total)
        if suggestions:
            logger.warning("Suggested reductions:")
            for suggestion in suggestions:
                logger.warning(f"  - {suggestion}") 