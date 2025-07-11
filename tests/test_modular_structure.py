"""
Test the new modular structure
"""

import sys
import types
from pathlib import Path
import pytest

# Create dummy modules for external dependencies
for name in ["requests", "schedule", "dateutil", "dateutil.parser"]:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

# Ensure the package is importable when tests run without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from awtempo.models import Config, TimeEntry, StaticTask, WindowMapping, TimeSlot
from awtempo.config_manager import ConfigurationError
from awtempo.activity_watch import ActivityWatchError
from awtempo.jira_tempo import JiraTempoError
from awtempo.time_processor import TimeProcessingError


def test_models_import():
    """Test that all models can be imported and instantiated"""
    # Test Config
    config = Config(
        jira_url="https://test.jira.com",
        jira_pat_token="test-token",
        worker_id="test-worker"
    )
    assert config.jira_url == "https://test.jira.com"
    assert config.worker_id == "test-worker"

    # Test TimeEntry
    from datetime import datetime
    entry = TimeEntry(
        jira_key="TEST-123",
        duration_seconds=3600,
        start_time=datetime.now(),
        description="Test entry"
    )
    assert entry.jira_key == "TEST-123"
    assert entry.duration_seconds == 3600

    # Test StaticTask
    task = StaticTask(
        name="Test Task",
        jira_key="TEST-123",
        time="09:00",
        duration_minutes=60,
        description="Test task",
        enabled=True
    )
    assert task.name == "Test Task"
    assert task.duration_minutes == 60

    # Test WindowMapping
    mapping = WindowMapping(
        name="Test Mapping",
        pattern="test",
        jira_key="TEST-123",
        description="Test mapping"
    )
    assert mapping.name == "Test Mapping"
    assert mapping.pattern == "test"

    # Test TimeSlot
    slot = TimeSlot(
        start_time=datetime.now(),
        end_time=datetime.now()
    )
    assert slot.start_time is not None
    assert slot.end_time is not None


def test_config_validation():
    """Test configuration validation"""
    # Test invalid URL
    with pytest.raises(ValueError, match="Invalid Jira URL format"):
        Config(
            jira_url="invalid-url",
            jira_pat_token="test-token",
            worker_id="test-worker"
        )

    # Test invalid PAT token
    with pytest.raises(ValueError, match="Jira PAT token is required"):
        Config(
            jira_url="https://test.jira.com",
            jira_pat_token="your-jira-pat-token",
            worker_id="test-worker"
        )

    # Test invalid working hours
    with pytest.raises(ValueError, match="Working hours per day must be between"):
        Config(
            jira_url="https://test.jira.com",
            jira_pat_token="test-token",
            worker_id="test-worker",
            working_hours_per_day=25
        )

    # Test invalid time rounding
    with pytest.raises(ValueError, match="Time rounding must be one of"):
        Config(
            jira_url="https://test.jira.com",
            jira_pat_token="test-token",
            worker_id="test-worker",
            time_rounding_minutes=20
        )


def test_static_task_validation():
    """Test static task validation"""
    # Test missing required fields
    with pytest.raises(ValueError, match="Static task must have name"):
        StaticTask(
            name="",
            jira_key="TEST-123",
            time="09:00",
            duration_minutes=60,
            description="Test task",
            enabled=True
        )

    # Test invalid duration
    with pytest.raises(ValueError, match="Duration must be positive"):
        StaticTask(
            name="Test Task",
            jira_key="TEST-123",
            time="09:00",
            duration_minutes=0,
            description="Test task",
            enabled=True
        )

    # Test invalid day of week
    with pytest.raises(ValueError, match="Invalid day of week"):
        StaticTask(
            name="Test Task",
            jira_key="TEST-123",
            time="09:00",
            duration_minutes=60,
            description="Test task",
            enabled=True,
            day_of_week="invalid-day"
        )


def test_window_mapping_validation():
    """Test window mapping validation"""
    # Test missing required fields
    with pytest.raises(ValueError, match="Window mapping must have name"):
        WindowMapping(
            name="",
            pattern="test",
            jira_key="TEST-123",
            description="Test mapping"
        )

    # Test invalid match type
    with pytest.raises(ValueError, match="Match type must be one of"):
        WindowMapping(
            name="Test Mapping",
            pattern="test",
            jira_key="TEST-123",
            description="Test mapping",
            match_type="invalid"
        )


def test_time_slot_validation():
    """Test time slot validation"""
    from datetime import datetime, timedelta
    
    # Test invalid time slot (start >= end)
    with pytest.raises(ValueError, match="Start time must be before end time"):
        now = datetime.now()
        TimeSlot(
            start_time=now,
            end_time=now
        )

    # Test valid time slot
    now = datetime.now()
    later = now + timedelta(hours=1)
    slot = TimeSlot(
        start_time=now,
        end_time=later
    )
    assert slot.duration_seconds == 3600
    assert slot.duration_minutes == 60


def test_exceptions_import():
    """Test that all custom exceptions can be imported"""
    assert ConfigurationError is not None
    assert ActivityWatchError is not None
    assert JiraTempoError is not None
    assert TimeProcessingError is not None 