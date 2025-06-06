#!/usr/bin/env python3
"""
ActivityWatch to Jira Tempo Automation Script
Automatically processes ActivityWatch data and updates Jira Tempo timesheets
"""

import json
import re
import requests
from datetime import datetime, timedelta, time
from dataclasses import dataclass
from typing import List, Dict, Optional
import sqlite3
import schedule
import logging
import argparse
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TimeEntry:
    """Represents a time entry for Jira Tempo"""
    jira_key: str
    duration_seconds: int
    start_time: datetime
    description: str
    is_static_task: bool = False
    original_timestamp: datetime = None

@dataclass
class Config:
    """Configuration settings"""
    jira_url: str
    jira_pat_token: str
    worker_id: str
    working_hours_per_day: float = 7.5
    time_rounding_minutes: int = 15  # Round to nearest 15, 30, or 60 minutes
    preview_file_path: str = "tempo_preview.json"
    default_processing_mode: str = "daily"
    mappings_file: str = "mappings.json"
    static_tasks_file: str = "static_tasks.json"
    log_level: str = "INFO"
    log_file: str = "activitywatch-tempo.log"
    minimum_activity_duration_seconds: int = 60
    jira_ticket_pattern: str = "SE-\\d+"
    excluded_apps: List[str] = None
    # Sequential time allocation settings
    sequential_allocation_enabled: bool = True
    work_start_time: str = "08:00"
    work_end_time: str = "17:30"
    gap_minutes: int = 5
    static_tasks_priority: bool = True

@dataclass
class StaticTask:
    """Represents a static daily/weekly task"""
    name: str
    jira_key: str
    time: str
    duration_minutes: int
    description: str
    enabled: bool
    day_of_week: str = None  # For weekly tasks

@dataclass
class WindowMapping:
    """Represents a window title to Jira key mapping"""
    name: str
    pattern: str
    jira_key: str
    description: str

@dataclass
class TimeSlot:
    """Represents an available time slot for sequential allocation"""
    start_time: datetime
    end_time: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def duration_seconds(self) -> int:
        return int((self.end_time - self.start_time).total_seconds())

class ActivityWatchProcessor:
    """Processes ActivityWatch data for Jira integration"""

    def __init__(self, config: Config, window_mappings: List[WindowMapping] = None):
        self.config = config
        self.aw_client_url = "http://localhost:5600"
        self.window_mappings = window_mappings or []

    def get_activity_data(self, date: datetime) -> Dict:
        """Fetch ActivityWatch data for a specific date"""
        try:
            # Get the bucket name (usually aw-watcher-window_[hostname])
            buckets_response = requests.get(f"{self.aw_client_url}/api/0/buckets")
            buckets = buckets_response.json()

            window_bucket = None
            for bucket_name in buckets.keys():
                if 'window' in bucket_name:
                    window_bucket = bucket_name
                    break

            if not window_bucket:
                logger.error("No window watcher bucket found")
                return {}

            # Query events for the day
            start_time = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = start_time + timedelta(days=1)

            query_params = {
                'start': start_time.isoformat(),
                'end': end_time.isoformat()
            }

            events_response = requests.get(
                f"{self.aw_client_url}/api/0/buckets/{window_bucket}/events",
                params=query_params
            )

            return events_response.json()

        except Exception as e:
            logger.error(f"Error fetching ActivityWatch data: {e}")
            return {}

    def check_window_mappings(self, window_title: str, app_name: str) -> Optional[tuple]:
        """Check if window title matches any configured mappings"""
        for mapping in self.window_mappings:
            # Use case-insensitive matching by default
            flags = re.IGNORECASE

            if re.search(mapping.pattern, window_title, flags) or re.search(mapping.pattern, app_name, flags):
                logger.info(f"[MATCH] Mapping matched: '{mapping.name}' -> {mapping.jira_key}")
                return (mapping.jira_key, mapping.description)
            else:
                logger.debug(f"[NO MATCH] Pattern '{mapping.pattern}' did not match title: '{window_title}' or app: '{app_name}'")

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
        """Process a day's activities into time entries"""
        events = self.get_activity_data(date)

        time_entries = []
        activity_blocks = {}  # Group by jira key

        # Add static tasks for this date (passed from AutomationManager)
        if static_tasks:
            static_entries = []
            day_name = date.strftime('%A').lower()

            for task in static_tasks:
                should_add = False

                # Check if this task should be added for this date
                if task.day_of_week is None:  # Daily task
                    should_add = True
                elif task.day_of_week == day_name:  # Weekly task on specific day
                    should_add = True

                if should_add:
                    # Parse time
                    time_parts = task.time.split(':')
                    task_time = time(int(time_parts[0]), int(time_parts[1]))

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

            time_entries.extend(static_entries)

        if not events:
            return time_entries

        # Process ActivityWatch events
        logger.info(f"[PROCESSING] Processing {len(events)} ActivityWatch events for grouping")
        processed_count = 0
        skipped_count = 0

        for event in events:
            window_title = event.get('data', {}).get('title', '')
            app_name = event.get('data', {}).get('app', '')
            duration = event.get('duration', 0)
            timestamp = datetime.fromisoformat(event.get('timestamp', '').replace('Z', '+00:00'))

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

        # Convert activity blocks to time entries
        logger.info(f"[CONVERT] Converting {len(activity_blocks)} activity blocks to time entries")
        for jira_key, block in activity_blocks.items():
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

        # Log processing summary
        logger.info(f"[SUMMARY] Processed {processed_count} events, skipped {skipped_count} events")
        logger.info(f"[RESULT] Created {len(time_entries)} time entries from {len(activity_blocks)} activity blocks")

        # Apply time rounding BEFORE sequential allocation
        for entry in time_entries:
            if not entry.is_static_task:  # Don't round static tasks
                original_duration = entry.duration_seconds
                entry.duration_seconds = self.round_time_duration(entry.duration_seconds)
                logger.debug(f"[ROUND] {entry.jira_key}: {original_duration}s -> {entry.duration_seconds}s ({entry.duration_seconds//60}min)")

        # Apply sequential time allocation if enabled
        if self.config.sequential_allocation_enabled:
            time_entries = self.arrange_sequential_times(time_entries, date)

        return self.validate_daily_hours(time_entries)

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

        return entries  # Return unchanged - no automatic scaling

    def parse_time_string(self, time_str: str, date: datetime) -> datetime:
        """Parse time string (HH:MM) and combine with date"""
        time_parts = time_str.split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        return datetime.combine(date.date(), time(hour, minute))

    def calculate_time_slots(self, static_tasks: List[TimeEntry], date: datetime) -> List[TimeSlot]:
        """Calculate available time slots between static tasks"""
        work_start = self.parse_time_string(self.config.work_start_time, date)
        work_end = self.parse_time_string(self.config.work_end_time, date)
        gap_duration = timedelta(minutes=self.config.gap_minutes)

        # Sort static tasks by start time
        static_tasks_sorted = sorted(static_tasks, key=lambda t: t.start_time)

        slots = []
        current_time = work_start

        for static_task in static_tasks_sorted:
            # Add slot before static task if there's time
            if current_time < static_task.start_time:
                slots.append(TimeSlot(current_time, static_task.start_time))

            # Move past static task (including gap)
            task_end = static_task.start_time + timedelta(seconds=static_task.duration_seconds)
            current_time = task_end + gap_duration

        # Add final slot after last static task
        if current_time < work_end:
            slots.append(TimeSlot(current_time, work_end))

        logger.debug(f"[SLOTS] Created {len(slots)} time slots for sequential allocation")
        for i, slot in enumerate(slots):
            logger.debug(f"[SLOT {i+1}] {slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')} ({slot.duration_minutes}min)")

        return slots

    def assign_entries_to_slots(self, activity_entries: List[TimeEntry], slots: List[TimeSlot]) -> bool:
        """Assign activity entries to available time slots sequentially"""
        if not slots:
            logger.warning("[SEQUENTIAL] No available time slots for activity entries")
            return False

        current_slot_index = 0
        current_time = slots[0].start_time
        gap_duration = timedelta(minutes=self.config.gap_minutes)
        overflow_entries = []

        # Sort activity entries by original timestamp (chronological order)
        activity_entries.sort(key=lambda e: e.original_timestamp or e.start_time)

        logger.info(f"[SEQUENTIAL] Assigning {len(activity_entries)} activity entries to {len(slots)} time slots")

        for entry in activity_entries:
            entry_duration = timedelta(seconds=entry.duration_seconds)
            assigned = False

            # Try to fit entry in current or subsequent slots
            while current_slot_index < len(slots):
                slot = slots[current_slot_index]

                # Ensure current_time is at least at the start of the current slot
                if current_time < slot.start_time:
                    current_time = slot.start_time

                # Check if entry fits in current slot
                if current_time + entry_duration <= slot.end_time:
                    # Assign entry to this time slot
                    entry.start_time = current_time
                    current_time += entry_duration + gap_duration
                    assigned = True
                    logger.debug(f"[ASSIGN] {entry.jira_key} -> {entry.start_time.strftime('%H:%M')} ({entry.duration_seconds//60}min)")
                    break
                else:
                    # Move to next slot
                    current_slot_index += 1
                    if current_slot_index < len(slots):
                        current_time = slots[current_slot_index].start_time
                        logger.debug(f"[NEXT SLOT] Moving to slot {current_slot_index + 1}")

            if not assigned:
                overflow_entries.append(entry)
                logger.debug(f"[OVERFLOW] {entry.jira_key} doesn't fit in available slots")

        if overflow_entries:
            logger.warning(f"[OVERFLOW] {len(overflow_entries)} entries don't fit in work day")
            return False

        return True

    def handle_overflow(self, activity_entries: List[TimeEntry], slots: List[TimeSlot], date: datetime):
        """Handle overflow by compressing gaps and extending work day"""
        logger.info("[OVERFLOW] Handling overflow entries")

        # Step 1: Try with compressed gaps (reduce by half)
        compressed_gap = max(0, self.config.gap_minutes // 2)
        logger.info(f"[OVERFLOW] Trying with compressed gaps: {compressed_gap}min")

        # Temporarily adjust gap setting
        original_gap = self.config.gap_minutes
        self.config.gap_minutes = compressed_gap

        # Recalculate slots with compressed gaps
        static_tasks = [e for e in activity_entries if e.is_static_task]
        compressed_slots = self.calculate_time_slots(static_tasks, date)

        # Try assignment again
        activity_only = [e for e in activity_entries if not e.is_static_task]
        if self.assign_entries_to_slots(activity_only, compressed_slots):
            logger.info("[OVERFLOW] Successfully fit entries with compressed gaps")
            return

        # Step 2: Extend work day if still overflowing
        logger.info("[OVERFLOW] Extending work day to fit remaining entries")

        # Calculate total overflow time needed
        total_activity_time = sum(e.duration_seconds for e in activity_only)
        total_available_time = sum(slot.duration_seconds for slot in compressed_slots)
        overflow_seconds = total_activity_time - total_available_time

        if overflow_seconds > 0:
            # Extend work end time
            work_end = self.parse_time_string(self.config.work_end_time, date)
            extended_end = work_end + timedelta(seconds=overflow_seconds)

            logger.info(f"[OVERFLOW] Extended work day to {extended_end.strftime('%H:%M')} (+{overflow_seconds//60}min)")

            # Create extended slot at end of day
            if compressed_slots:
                last_slot = compressed_slots[-1]
                last_slot.end_time = extended_end
            else:
                # No slots available, create one big slot
                work_start = self.parse_time_string(self.config.work_start_time, date)
                compressed_slots = [TimeSlot(work_start, extended_end)]

            # Final assignment attempt
            self.assign_entries_to_slots(activity_only, compressed_slots)

        # Restore original gap setting
        self.config.gap_minutes = original_gap

    def arrange_sequential_times(self, entries: List[TimeEntry], date: datetime) -> List[TimeEntry]:
        """Arrange time entries sequentially with static tasks taking priority"""
        if not self.config.sequential_allocation_enabled:
            return entries

        logger.info("[SEQUENTIAL] Starting sequential time allocation")

        # Separate static tasks from activity entries
        static_tasks = [e for e in entries if e.is_static_task]
        activity_entries = [e for e in entries if not e.is_static_task]

        logger.info(f"[SEQUENTIAL] {len(static_tasks)} static tasks, {len(activity_entries)} activity entries")

        if not activity_entries:
            logger.info("[SEQUENTIAL] No activity entries to arrange")
            return entries

        # Static tasks keep their exact times (highest priority)
        logger.info("[SEQUENTIAL] Static tasks maintain their configured times")
        for task in static_tasks:
            logger.debug(f"[STATIC] {task.jira_key} at {task.start_time.strftime('%H:%M')} ({task.duration_seconds//60}min)")

        # Calculate available time slots between static tasks
        available_slots = self.calculate_time_slots(static_tasks, date)

        if not available_slots:
            logger.warning("[SEQUENTIAL] No available time slots found")
            return entries

        # Try to assign activity entries to available slots
        if self.assign_entries_to_slots(activity_entries, available_slots):
            logger.info("[SEQUENTIAL] Successfully assigned all entries to time slots")
        else:
            # Handle overflow
            self.handle_overflow(entries, available_slots, date)

        # Log final arrangement
        all_entries = static_tasks + activity_entries
        all_entries.sort(key=lambda e: e.start_time)

        logger.info("[SEQUENTIAL] Final time arrangement:")
        for entry in all_entries:
            entry_type = "STATIC" if entry.is_static_task else "ACTIVITY"
            logger.info(f"[{entry_type}] {entry.start_time.strftime('%H:%M')}-{(entry.start_time + timedelta(seconds=entry.duration_seconds)).strftime('%H:%M')} {entry.jira_key} ({entry.duration_seconds//60}min)")

        return all_entries

class JiraTempoIntegration:
    """Handles Jira Tempo API integration"""

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {config.jira_pat_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

    def get_current_user(self) -> Optional[Dict]:
        """Get current user information from Jira API"""
        try:
            response = self.session.get(f"{self.config.jira_url}/rest/api/2/myself")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to get current user: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error getting current user: {e}")
            return None

    def get_worker_id(self) -> Optional[str]:
        """Get the worker ID for the current user"""
        user_info = self.get_current_user()
        if user_info:
            # Try different possible fields for worker ID
            worker_id = user_info.get('key') or user_info.get('accountId') or user_info.get('name')
            if worker_id:
                logger.info(f"Auto-detected worker_id: {worker_id}")
                return worker_id
            else:
                logger.warning("Could not determine worker_id from user info")
                logger.debug(f"User info: {user_info}")
        return None

    def validate_jira_key(self, jira_key: str) -> bool:
        """Validate that a Jira key exists"""
        try:
            response = self.session.get(f"{self.config.jira_url}/rest/api/2/issue/{jira_key}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Error validating Jira key {jira_key}: {e}")
            return False

    def submit_time_entry(self, entry: TimeEntry) -> bool:
        """Submit a time entry to Jira Tempo"""
        try:
            # Validate Jira key first
            if not self.validate_jira_key(entry.jira_key):
                logger.error(f"Invalid Jira key: {entry.jira_key}")
                return False

            # Convert to Tempo format matching your working API structure
            tempo_entry = {
                "worker": self.config.worker_id,
                "comment": entry.description,
                "started": entry.start_time.strftime("%Y-%m-%dT%H:%M:%S.000"),
                "timeSpentSeconds": entry.duration_seconds,
                "originTaskId": entry.jira_key,
                "originId": -1
            }

            # Submit to Tempo API (with trailing slash)
            response = self.session.post(
                f"{self.config.jira_url}/rest/tempo-timesheets/4/worklogs/",
                json=tempo_entry
            )

            if response.status_code in [200, 201]:
                logger.info(f"Successfully logged {entry.duration_seconds/3600:.2f}h to {entry.jira_key}")
                return True
            else:
                logger.error(f"Failed to log time to {entry.jira_key}: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error submitting time entry: {e}")
            return False

    def submit_daily_entries(self, entries: List[TimeEntry]) -> bool:
        """Submit all daily time entries"""
        success_count = 0

        for entry in entries:
            if self.submit_time_entry(entry):
                success_count += 1

        logger.info(f"Successfully submitted {success_count}/{len(entries)} time entries")
        return success_count == len(entries)

class AutomationManager:
    """Main automation manager"""

    def __init__(self, config_file: str = "config.json"):
        self.config = self.load_config(config_file)
        self.window_mappings = self.load_window_mappings()
        self.static_tasks = self.load_static_tasks()
        self.processor = ActivityWatchProcessor(self.config, self.window_mappings)
        self.jira_integration = JiraTempoIntegration(self.config)

    def load_config(self, config_file: str) -> Config:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)

            # Load sequential allocation settings
            seq_config = config_data.get('sequential_time_allocation', {})

            # Auto-detect worker_id if not provided or set to placeholder
            worker_id = config_data.get('worker_id', 'auto')
            if worker_id in ['auto', 'your-worker-id', '']:
                # Try to auto-detect worker_id using the PAT token
                try:
                    # Create a minimal session for auto-detection
                    session = requests.Session()
                    session.headers.update({
                        'Authorization': f'Bearer {config_data["jira_pat_token"]}',
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    })

                    response = session.get(f"{config_data['jira_url']}/rest/api/2/myself")
                    if response.status_code == 200:
                        user_info = response.json()
                        detected_worker_id = user_info.get('key') or user_info.get('accountId') or user_info.get('name')
                        if detected_worker_id:
                            worker_id = detected_worker_id
                            logger.info(f"Auto-detected worker_id: {worker_id}")
                        else:
                            logger.warning("Could not determine worker_id from user info")
                            worker_id = config_data.get('worker_id', 'UNKNOWN')
                    else:
                        logger.warning(f"Failed to auto-detect worker_id: {response.status_code}")
                        worker_id = config_data.get('worker_id', 'UNKNOWN')
                except Exception as e:
                    logger.warning(f"Error auto-detecting worker_id: {e}")
                    worker_id = config_data.get('worker_id', 'UNKNOWN')

            config = Config(
                jira_url=config_data['jira_url'],
                jira_pat_token=config_data['jira_pat_token'],
                worker_id=worker_id,
                working_hours_per_day=config_data.get('working_hours_per_day', 7.5),
                time_rounding_minutes=config_data.get('time_rounding_minutes', 15),
                preview_file_path=config_data.get('preview_file_path', 'tempo_preview.json'),
                default_processing_mode=config_data.get('default_processing_mode', 'daily'),
                mappings_file=config_data.get('mappings_file', 'mappings.json'),
                static_tasks_file=config_data.get('static_tasks_file', 'static_tasks.json'),
                log_level=config_data.get('log_level', 'INFO'),
                log_file=config_data.get('log_file', 'activitywatch-tempo.log'),
                minimum_activity_duration_seconds=config_data.get('minimum_activity_duration_seconds', 60),
                jira_ticket_pattern=config_data.get('jira_ticket_pattern', 'SE-\\d+'),
                excluded_apps=config_data.get('excluded_apps', []),
                # Sequential time allocation settings
                sequential_allocation_enabled=seq_config.get('enabled', True),
                work_start_time=seq_config.get('work_start_time', '08:00'),
                work_end_time=seq_config.get('work_end_time', '17:30'),
                gap_minutes=seq_config.get('gap_minutes', 5),
                static_tasks_priority=seq_config.get('static_tasks_priority', True)
            )

            # Configure logging based on config
            self.setup_logging(config)

            return config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

    def setup_logging(self, config: Config):
        """Setup logging configuration"""
        # Clear existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

        # Set log level
        log_level = getattr(logging, config.log_level.upper(), logging.INFO)
        logger.setLevel(log_level)

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # File handler
        file_handler = logging.FileHandler(config.log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Console handler (less verbose)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)  # Only warnings and errors to console
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    def load_window_mappings(self) -> List[WindowMapping]:
        """Load window title mappings from JSON file"""
        try:
            with open(self.config.mappings_file, 'r') as f:
                mappings_data = json.load(f)

            mappings = []
            for mapping_data in mappings_data.get('mappings', []):
                mapping = WindowMapping(
                    name=mapping_data['name'],
                    pattern=mapping_data['pattern'],
                    jira_key=mapping_data['jira_key'],
                    description=mapping_data['description']
                )
                mappings.append(mapping)

            logger.info(f"Loaded {len(mappings)} mappings")
            return mappings

        except FileNotFoundError:
            logger.warning(f"Mappings file not found: {self.config.mappings_file}")
            return []
        except Exception as e:
            logger.error(f"Error loading mappings: {e}")
            return []

    def load_static_tasks(self) -> List[StaticTask]:
        """Load static tasks from JSON file"""
        try:
            with open(self.config.static_tasks_file, 'r') as f:
                tasks_data = json.load(f)

            tasks = []

            # Load daily tasks
            for task_data in tasks_data.get('daily_tasks', []):
                if task_data.get('enabled', False):
                    task = StaticTask(
                        name=task_data['name'],
                        jira_key=task_data['jira_key'],
                        time=task_data['time'],
                        duration_minutes=task_data['duration_minutes'],
                        description=task_data['description'],
                        enabled=task_data['enabled']
                    )
                    tasks.append(task)

            # Load weekly tasks
            for task_data in tasks_data.get('weekly_tasks', []):
                if task_data.get('enabled', False):
                    task = StaticTask(
                        name=task_data['name'],
                        jira_key=task_data['jira_key'],
                        time=task_data['time'],
                        duration_minutes=task_data['duration_minutes'],
                        description=task_data['description'],
                        enabled=task_data['enabled'],
                        day_of_week=task_data.get('day_of_week')
                    )
                    tasks.append(task)

            logger.info(f"Loaded {len(tasks)} enabled static tasks")
            return tasks

        except FileNotFoundError:
            logger.warning(f"Static tasks file not found: {self.config.static_tasks_file}")
            return []
        except Exception as e:
            logger.error(f"Error loading static tasks: {e}")
            return []

    def add_static_tasks(self, date: datetime) -> List[TimeEntry]:
        """Add static tasks for the given date"""
        entries = []
        day_name = date.strftime('%A').lower()

        for task in self.static_tasks:
            should_add = False

            # Check if this task should be added for this date
            if task.day_of_week is None:  # Daily task
                should_add = True
            elif task.day_of_week == day_name:  # Weekly task on specific day
                should_add = True

            if should_add:
                # Parse time
                time_parts = task.time.split(':')
                task_time = time(int(time_parts[0]), int(time_parts[1]))

                entry = TimeEntry(
                    jira_key=task.jira_key,
                    duration_seconds=task.duration_minutes * 60,
                    start_time=datetime.combine(date.date(), task_time),
                    description=task.description
                )
                entries.append(entry)
                logger.info(f"Added static task: {task.name} ({task.duration_minutes}min)")

        return entries

    def process_yesterday(self):
        """Process yesterday's activities and submit to Jira"""
        yesterday = datetime.now() - timedelta(days=1)
        logger.info(f"Processing activities for {yesterday.strftime('%Y-%m-%d')}")

        entries = self.processor.process_daily_activities(yesterday, self.static_tasks)
        if entries:
            self.jira_integration.submit_daily_entries(entries)
        else:
            logger.info("No time entries found for yesterday")

    def process_specific_date(self, date: datetime):
        """Process activities for a specific date"""
        logger.info(f"Processing activities for {date.strftime('%Y-%m-%d')}")

        entries = self.processor.process_daily_activities(date, self.static_tasks)
        if entries:
            self.jira_integration.submit_daily_entries(entries)
        else:
            logger.info(f"No time entries found for {date.strftime('%Y-%m-%d')}")

    def process_weekly_activities(self, start_date: datetime) -> List[TimeEntry]:
        """Process a week's activities into time entries"""
        all_entries = []

        # Process Monday to Friday
        for day_offset in range(5):  # 0-4 for Mon-Fri
            current_date = start_date + timedelta(days=day_offset)
            daily_entries = self.processor.process_daily_activities(current_date, self.static_tasks)
            all_entries.extend(daily_entries)

        return all_entries

    def suggest_reductions(self, entries: List[TimeEntry], excess_seconds: int) -> List[str]:
        """Analyze entries and suggest what to reduce when over daily limit"""
        suggestions = []
        excess_hours = excess_seconds / 3600

        # Group entries by type for analysis
        admin_entries = [e for e in entries if 'admin' in e.description.lower() or 'planning' in e.description.lower() or 'review' in e.description.lower()]
        short_entries = [e for e in entries if e.duration_seconds <= 1800]  # 30 minutes or less
        duplicate_tickets = {}

        # Find duplicate tickets (multiple entries for same Jira key)
        for entry in entries:
            if entry.jira_key in duplicate_tickets:
                duplicate_tickets[entry.jira_key].append(entry)
            else:
                duplicate_tickets[entry.jira_key] = [entry]

        multi_entries = {k: v for k, v in duplicate_tickets.items() if len(v) > 1}

        # Generate suggestions based on analysis
        if admin_entries:
            total_admin_hours = sum(e.duration_seconds for e in admin_entries) / 3600
            if total_admin_hours >= excess_hours:
                suggestions.append(f"Admin/overhead tasks: {total_admin_hours:.1f}h total → Could reduce by {excess_hours:.1f}h")

        if short_entries:
            for entry in short_entries[:3]:  # Show top 3 short entries
                hours = entry.duration_seconds / 3600
                suggestions.append(f"{entry.jira_key} (Short activity): {hours:.1f}h → Could remove entirely (-{hours:.1f}h)")


        if multi_entries:
            for jira_key, entry_list in list(multi_entries.items())[:2]:  # Show top 2
                total_hours = sum(e.duration_seconds for e in entry_list) / 3600
                suggestions.append(f"{jira_key} (Multiple entries): {total_hours:.1f}h total → Could consolidate and reduce")

        return suggestions[:5]  # Return top 5 suggestions

    def create_preview_file(self, entries: List[TimeEntry], start_date: datetime, end_date: datetime, mode: str):
        """Create a preview file with time entries for manual review"""
        total_seconds = sum(entry.duration_seconds for entry in entries)
        max_seconds = self.config.working_hours_per_day * 3600

        preview_data = {
            "generated_date": datetime.now().isoformat(),
            "processing_period": {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "mode": mode
            },
            "total_hours": round(total_seconds / 3600, 2),
            "daily_limit": self.config.working_hours_per_day,
            "entries": []
        }

        # Add overflow warning if over limit
        if total_seconds > max_seconds:
            excess_seconds = total_seconds - max_seconds
            excess_hours = excess_seconds / 3600
            preview_data["overflow_warning"] = {
                "message": f"Total time ({preview_data['total_hours']}h) exceeds daily limit ({self.config.working_hours_per_day}h) by {excess_hours:.1f}h",
                "excess_hours": round(excess_hours, 1),
                "suggestions": self.suggest_reductions(entries, excess_seconds)
            }

        for entry in entries:
            preview_data["entries"].append({
                "jira_key": entry.jira_key,
                "duration_seconds": entry.duration_seconds,
                "start_time": entry.start_time.isoformat(),
                "comment": entry.description
            })

        with open(self.config.preview_file_path, 'w') as f:
            json.dump(preview_data, f, indent=2)

        logger.info(f"Preview file created: {self.config.preview_file_path}")
        logger.info(f"Total entries: {len(entries)}")
        logger.info(f"Total hours: {preview_data['total_hours']}")

        # Display summary with overflow warning
        print(f"\n=== PREVIEW SUMMARY ===")
        print(f"Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} ({mode})")
        print(f"Total Hours: {preview_data['total_hours']}")
        print(f"Total Entries: {len(entries)}")

        # Show overflow warning if applicable
        if total_seconds > max_seconds:
            excess_hours = (total_seconds - max_seconds) / 3600
            print(f"\n⚠️  WARNING: Time Overflow Detected ⚠️")
            print(f"Total Time: {preview_data['total_hours']}h ({excess_hours:.1f}h over {self.config.working_hours_per_day}h limit)")

            suggestions = self.suggest_reductions(entries, total_seconds - max_seconds)
            if suggestions:
                print(f"\nSuggestions for reduction:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"  {i}. {suggestion}")

            print(f"\n📝 Edit {self.config.preview_file_path} to adjust entries before submitting.")
            print(f"💡 Run 'python {sys.argv[0]} --submit' when ready.")
        else:
            print(f"\n✅ Time within daily limit ({self.config.working_hours_per_day}h)")
            print(f"📝 Review {self.config.preview_file_path} and run 'python {sys.argv[0]} --submit' to submit.")

        print(f"\nEntries:")
        for entry in entries:
            hours = entry.duration_seconds / 3600
            print(f"  {entry.jira_key}: {hours:.2f}h - {entry.description}")
        print(f"\nPreview saved to: {self.config.preview_file_path}")

    def load_preview_file(self) -> List[TimeEntry]:
        """Load time entries from preview file"""
        try:
            with open(self.config.preview_file_path, 'r') as f:
                preview_data = json.load(f)

            entries = []
            for entry_data in preview_data["entries"]:
                # Handle both old "description" and new "comment" field names for backward compatibility
                description = entry_data.get("comment") or entry_data.get("description", "")

                entry = TimeEntry(
                    jira_key=entry_data["jira_key"],
                    duration_seconds=entry_data["duration_seconds"],
                    start_time=datetime.fromisoformat(entry_data["start_time"]),
                    description=description
                )
                entries.append(entry)

            logger.info(f"Loaded {len(entries)} entries from preview file")
            return entries

        except FileNotFoundError:
            logger.error(f"Preview file not found: {self.config.preview_file_path}")
            logger.error("Run with --preview first to generate the preview file")
            return []
        except Exception as e:
            logger.error(f"Error loading preview file: {e}")
            return []

    def submit_preview_entries(self):
        """Submit time entries from preview file to Jira Tempo"""
        entries = self.load_preview_file()
        if not entries:
            return False

        # Validate total hours against daily limit
        total_hours = sum(entry.duration_seconds for entry in entries) / 3600

        # Check if still over daily limit (block submission)
        if total_hours > self.config.working_hours_per_day:
            excess_hours = total_hours - self.config.working_hours_per_day
            print(f"\n❌ Submission blocked: Total time is {total_hours:.1f}h ({excess_hours:.1f}h over {self.config.working_hours_per_day}h limit)")
            print(f"Please edit {self.config.preview_file_path} to reduce time by {excess_hours:.1f}h before submitting.")

            # Show current suggestions for reduction
            suggestions = self.suggest_reductions(entries, int(excess_hours * 3600))
            if suggestions:
                print(f"\nSuggestions for reduction:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"  {i}. {suggestion}")

            return False

        # Check weekly limit (warning only, don't block)
        if total_hours > self.config.working_hours_per_day * 5:  # Max for a week
            logger.warning(f"Total hours ({total_hours:.2f}) exceeds weekly limit")

        # All validations passed - submit entries
        print(f"\n✅ Submitting {len(entries)} entries ({total_hours:.1f}h total)...")
        success = self.jira_integration.submit_daily_entries(entries)

        if success:
            # Archive the preview file
            archive_name = f"{self.config.preview_file_path}.submitted_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            Path(self.config.preview_file_path).rename(archive_name)
            logger.info(f"Preview file archived as: {archive_name}")
            print(f"✅ Successfully submitted all entries to Tempo!")
            print(f"📁 Preview file archived as: {archive_name}")
        else:
            print(f"❌ Some entries failed to submit. Check logs for details.")

        return success

    def generate_preview(self, mode: str = None, date: datetime = None):
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

        if mode == "weekly":
            entries = self.process_weekly_activities(start_date)
        else:
            entries = self.processor.process_daily_activities(start_date, self.static_tasks)

        if entries:
            self.create_preview_file(entries, start_date, end_date, mode)
        else:
            logger.info(f"No time entries found for the specified {mode} period")

    def start_scheduler(self):
        """Start the automated scheduler"""
        # Schedule daily processing at 8 AM
        schedule.every().day.at("08:00").do(self.process_yesterday)

        logger.info("Scheduler started. Daily processing at 8:00 AM")

        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="ActivityWatch to Jira Tempo automation script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate daily preview for yesterday
  python activitywatch-tempo.py --preview

  # Generate weekly preview for last week
  python activitywatch-tempo.py --preview --weekly

  # Generate preview for specific date
  python activitywatch-tempo.py --preview --date 2024-01-15

  # Submit preview entries to Tempo
  python activitywatch-tempo.py --submit

  # Direct submission (legacy mode)
  python activitywatch-tempo.py --direct

  # Start scheduler
  python activitywatch-tempo.py --scheduler
        """
    )

    parser.add_argument(
        '--preview',
        action='store_true',
        help='Generate preview file for manual review'
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
        '--config',
        type=str,
        default='config.json',
        help='Configuration file path (default: config.json)'
    )

    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_arguments()

    try:
        manager = AutomationManager(args.config)
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        sys.exit(1)

    # Parse date if provided
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)

    # Determine processing mode
    mode = "weekly" if args.weekly else "daily"

    # Execute based on arguments
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
        manager.generate_preview(manager.config.default_processing_mode)

if __name__ == "__main__":
    main()
