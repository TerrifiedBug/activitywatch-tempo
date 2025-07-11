"""
Data models for ActivityWatch Tempo integration
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class TimeEntry:
    """Represents a time entry for Jira Tempo"""
    jira_key: str
    duration_seconds: int
    start_time: datetime
    description: str
    is_static_task: bool = False
    original_timestamp: Optional[datetime] = None


@dataclass
class Config:
    """Configuration settings"""
    jira_url: str
    jira_pat_token: str
    worker_id: str
    working_hours_per_day: float = 7.5
    # Round duration UP to the next 15, 30, or 60 minute interval
    time_rounding_minutes: int = 15
    preview_file_path: str = "tempo_preview.json"
    default_processing_mode: str = "daily"
    mappings_file: str = "mappings.json"
    static_tasks_file: str = "static_tasks.json"
    log_level: str = "INFO"
    log_file: str = "activitywatch-tempo.log"
    minimum_activity_duration_seconds: int = 60
    jira_ticket_pattern: str = "SE-\\d+"
    excluded_apps: Optional[List[str]] = None
    # Lunch break configuration
    lunch_enabled: bool = False
    lunch_time: str = "13:00"
    lunch_duration_minutes: int = 30
    # Sequential time allocation settings
    sequential_allocation_enabled: bool = True
    work_start_time: str = "08:00"
    work_end_time: str = "17:30"
    gap_minutes: int = 5
    static_tasks_priority: bool = True

    def __post_init__(self):
        """Validate configuration after initialization"""
        if not self.jira_url.startswith(('http://', 'https://')):
            raise ValueError("Invalid Jira URL format. Must start with http:// or https://")
        
        if not self.jira_pat_token or self.jira_pat_token == "your-jira-pat-token":
            raise ValueError("Jira PAT token is required and cannot be the default placeholder")
        
        if self.working_hours_per_day <= 0 or self.working_hours_per_day > 24:
            raise ValueError("Working hours per day must be between 0 and 24")
        
        if self.time_rounding_minutes not in [1, 5, 10, 15, 30, 60]:
            raise ValueError("Time rounding must be one of: 1, 5, 10, 15, 30, 60 minutes")


@dataclass
class StaticTask:
    """Represents a static daily/weekly task"""
    name: str
    jira_key: str
    time: str
    duration_minutes: int
    description: str
    enabled: bool
    day_of_week: Optional[str] = None  # For weekly tasks

    def __post_init__(self):
        """Validate static task after initialization"""
        if not self.name or not self.jira_key or not self.description:
            raise ValueError("Static task must have name, jira_key, and description")
        
        if self.duration_minutes <= 0:
            raise ValueError("Duration must be positive")
        
        if self.day_of_week and self.day_of_week not in [
            'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
        ]:
            raise ValueError("Invalid day of week")


@dataclass
class WindowMapping:
    """Represents a window title to Jira key mapping"""
    name: str
    pattern: str
    jira_key: str
    description: str
    match_type: str = "both"  # "title", "app", or "both"
    enabled: bool = True

    def __post_init__(self):
        """Validate window mapping after initialization"""
        if not self.name or not self.pattern or not self.jira_key or not self.description:
            raise ValueError("Window mapping must have name, pattern, jira_key, and description")
        
        if self.match_type not in ["title", "app", "both"]:
            raise ValueError("Match type must be one of: title, app, both")


@dataclass
class TimeSlot:
    """Represents an available time slot for sequential allocation"""
    start_time: datetime
    end_time: datetime

    def __post_init__(self):
        """Validate time slot after initialization"""
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time")

    @property
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def duration_seconds(self) -> int:
        return int((self.end_time - self.start_time).total_seconds()) 