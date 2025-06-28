import sys
import types
from pathlib import Path
import pytest

# Create dummy modules for external dependencies not installed in test env
for name in ["requests", "schedule", "dateutil", "dateutil.parser"]:
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

# Ensure the package is importable when tests run without installation
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from awtempo.cli import ActivityWatchProcessor, Config


@pytest.mark.parametrize(
    "rounding_minutes, duration_seconds, expected",
    [
        (15, 0, 0),
        (15, 1, 15 * 60),
        (15, 900, 15 * 60),
        (15, 901, 30 * 60),
        (30, 1, 30 * 60),
        (30, 1800 - 1, 30 * 60),
        (30, 1800, 30 * 60),
        (30, 1800 + 1, 60 * 60),
        (60, 1, 60 * 60),
        (60, 3600 - 1, 60 * 60),
        (60, 3600, 60 * 60),
        (60, 3600 + 1, 2 * 60 * 60),
    ],
)
def test_round_time_duration(rounding_minutes, duration_seconds, expected):
    cfg = Config(
        jira_url="https://example.com",
        jira_pat_token="dummy",
        worker_id="worker",
        time_rounding_minutes=rounding_minutes,
    )
    processor = ActivityWatchProcessor(cfg)
    assert processor.round_time_duration(duration_seconds) == expected
