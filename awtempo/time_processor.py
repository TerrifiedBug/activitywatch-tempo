"""
Time processing logic for ActivityWatch Tempo
"""

import logging
import math
from datetime import datetime, timedelta
from typing import List

from .models import Config, TimeEntry, TimeSlot, StaticTask

logger = logging.getLogger(__name__)


class TimeProcessingError(Exception):
    """Raised when there's an issue with time processing"""
    pass


class TimeProcessor:
    """Handles time processing logic including sequential allocation and rounding"""

    def __init__(self, config: Config):
        self.config = config

    def round_time_duration(self, duration_seconds: int) -> int:
        """Round time duration UP to the next configured interval"""
        rounding_seconds = self.config.time_rounding_minutes * 60

        # Round UP to next interval (ceiling)
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
        self._log_overflow_items(entries, int(max_seconds))

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

    def _suggest_reductions(self, entries: List[TimeEntry], excess_seconds: int) -> List[str]:
        """Suggest how to reduce time to fit within daily limit"""
        suggestions = []
        
        # Sort by duration (largest first)
        sorted_entries = sorted(entries, key=lambda e: e.duration_seconds, reverse=True)
        
        for entry in sorted_entries:
            if entry.duration_seconds > excess_seconds:
                reduction_needed = entry.duration_seconds - excess_seconds
                suggestions.append(f"Reduce {entry.jira_key} by {reduction_needed/3600:.1f}h")
                break
            else:
                suggestions.append(f"Remove {entry.jira_key} ({entry.duration_seconds/3600:.1f}h)")
                excess_seconds -= entry.duration_seconds
                
        return suggestions

    def parse_time_string(self, time_str: str, date: datetime) -> datetime:
        """Parse time string (HH:MM) and combine with date"""
        try:
            time_parts = time_str.split(':')
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time format")
                
            from datetime import time
            return datetime.combine(date.date(), time(hour, minute))
        except (ValueError, IndexError) as e:
            raise TimeProcessingError(f"Invalid time format '{time_str}': {e}")

    def calculate_time_slots(self, static_tasks: List[TimeEntry], date: datetime) -> List[TimeSlot]:
        """Calculate available time slots between static tasks and lunch break"""
        work_start = self.parse_time_string(self.config.work_start_time, date)
        work_end = self.parse_time_string(self.config.work_end_time, date)
        gap_duration = timedelta(minutes=self.config.gap_minutes)

        # Combine static tasks with lunch break if enabled
        all_blocked_times = list(static_tasks)

        if self.config.lunch_enabled:
            lunch_start = self.parse_time_string(self.config.lunch_time, date)
            lunch_duration = timedelta(minutes=self.config.lunch_duration_minutes)

            # Create a virtual lunch "task" for time slot calculation
            lunch_entry = TimeEntry(
                jira_key="LUNCH",
                duration_seconds=self.config.lunch_duration_minutes * 60,
                start_time=lunch_start,
                description="Lunch break (blocked time)",
                is_static_task=True
            )
            all_blocked_times.append(lunch_entry)
            logger.debug(f"[LUNCH] Added lunch break: {lunch_start.strftime('%H:%M')} ({self.config.lunch_duration_minutes}min)")

        # Sort all blocked times by start time
        blocked_times_sorted = sorted(all_blocked_times, key=lambda t: t.start_time)

        slots = []
        current_time = work_start

        for blocked_time in blocked_times_sorted:
            # Add slot before blocked time if there's time
            if current_time < blocked_time.start_time:
                slots.append(TimeSlot(current_time, blocked_time.start_time))

            # Move past blocked time (including gap, but not for lunch)
            time_end = blocked_time.start_time + timedelta(seconds=blocked_time.duration_seconds)
            if blocked_time.jira_key == "LUNCH":
                current_time = time_end  # No gap after lunch
            else:
                current_time = time_end + gap_duration

        # Add final slot after last blocked time
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

    def process_time_entries(self, entries: List[TimeEntry], date: datetime) -> List[TimeEntry]:
        """Process time entries with rounding and sequential allocation"""
        # Apply time rounding BEFORE sequential allocation
        for entry in entries:
            if not entry.is_static_task:  # Don't round static tasks
                original_duration = entry.duration_seconds
                entry.duration_seconds = self.round_time_duration(entry.duration_seconds)
                logger.debug(f"[ROUND] {entry.jira_key}: {original_duration}s -> {entry.duration_seconds}s ({entry.duration_seconds//60}min)")

        # Apply sequential time allocation if enabled
        if self.config.sequential_allocation_enabled:
            entries = self.arrange_sequential_times(entries, date)

        return self.validate_daily_hours(entries) 