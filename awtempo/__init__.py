__all__ = ["main", "Config", "TimeEntry", "StaticTask", "WindowMapping", "TimeSlot"]
from .models import Config, TimeEntry, StaticTask, WindowMapping, TimeSlot
from .cli import main
__version__ = "0.2.0"
