"""
Configuration management for ActivityWatch Tempo
"""

import json
import logging
import os
import requests
from pathlib import Path
from typing import Optional

from .models import Config, WindowMapping, StaticTask

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when there's an issue with configuration"""
    pass


def merge_json_defaults(default_path: Path, user_path: Path) -> bool:
    """Merge keys from ``default_path`` into ``user_path`` without overwriting existing values."""
    if not default_path.exists():
        return False
    
    if not user_path.exists():
        import shutil
        shutil.copy(default_path, user_path)
        logger.info(f"Created {user_path} from defaults")
        return True

    with open(default_path, 'r') as f:
        default_data = json.load(f)
    with open(user_path, 'r') as f:
        user_data = json.load(f)

    changed = False

    def merge(d, u):
        nonlocal changed
        for k, v in d.items():
            if k not in u:
                u[k] = v
                changed = True
            elif isinstance(v, dict) and isinstance(u.get(k), dict):
                merge(v, u[k])

    merge(default_data, user_data)

    if changed:
        with open(user_path, 'w') as f:
            json.dump(user_data, f, indent=2)
        logger.info(f"Updated {user_path} with new settings")

    return changed


def update_config_files(config_path: str, config: Optional[Config] = None) -> None:
    """Update user configuration, mappings and static task files from defaults."""
    defaults_dir = Path(__file__).parent / 'defaults'
    config_file = Path(config_path)
    merge_json_defaults(defaults_dir / 'config.json', config_file)

    if config is None:
        try:
            with open(config_file, 'r') as f:
                data = json.load(f)
            mappings_file = data.get('mappings_file', 'mappings.json')
            static_file = data.get('static_tasks_file', 'static_tasks.json')
        except Exception as e:
            logger.error(f"Could not read config for update: {e}")
            return
    else:
        mappings_file = config.mappings_file
        static_file = config.static_tasks_file

    merge_json_defaults(defaults_dir / 'mappings.json', Path(mappings_file))
    merge_json_defaults(defaults_dir / 'static_tasks.json', Path(static_file))


def validate_config_data(config_data: dict) -> None:
    """Validate configuration data structure and values"""
    required_fields = ['jira_url', 'jira_pat_token']
    for field in required_fields:
        if field not in config_data:
            raise ConfigurationError(f"Missing required field: {field}")
    
    # Validate URL format
    if not config_data['jira_url'].startswith(('http://', 'https://')):
        raise ConfigurationError("Invalid Jira URL format. Must start with http:// or https://")
    
    # Validate PAT token
    if not config_data['jira_pat_token'] or config_data['jira_pat_token'] == "your-jira-pat-token":
        raise ConfigurationError("Jira PAT token is required and cannot be the default placeholder")
    
    # Validate working hours
    working_hours = config_data.get('working_hours_per_day', 7.5)
    if working_hours <= 0 or working_hours > 24:
        raise ConfigurationError("Working hours per day must be between 0 and 24")
    
    # Validate time rounding
    time_rounding = config_data.get('time_rounding_minutes', 15)
    if time_rounding not in [1, 5, 10, 15, 30, 60]:
        raise ConfigurationError("Time rounding must be one of: 1, 5, 10, 15, 30, 60 minutes")


def auto_detect_worker_id(jira_url: str, pat_token: str) -> str:
    """Auto-detect worker ID using the PAT token"""
    try:
        session = requests.Session()
        session.headers.update({
            'Authorization': f'Bearer {pat_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })

        response = session.get(f"{jira_url}/rest/api/2/myself", timeout=10)
        if response.status_code == 200:
            user_info = response.json()
            detected_worker_id = user_info.get('key') or user_info.get('accountId') or user_info.get('name')
            if detected_worker_id:
                logger.info(f"Auto-detected worker_id: {detected_worker_id}")
                return detected_worker_id
            else:
                logger.warning("Could not determine worker_id from user info")
                return "UNKNOWN"
        else:
            logger.warning(f"Failed to auto-detect worker_id: {response.status_code}")
            return "UNKNOWN"
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error auto-detecting worker_id: {e}")
        return "UNKNOWN"


def load_config(config_file: str) -> Config:
    """Load and validate configuration from JSON file"""
    try:
        with open(config_file, 'r') as f:
            config_data = json.load(f)

        # Validate configuration data
        validate_config_data(config_data)

        # Load sequential allocation settings
        seq_config = config_data.get('sequential_time_allocation', {})

        # Auto-detect worker_id if not provided or set to placeholder
        worker_id = config_data.get('worker_id', 'auto')
        if worker_id in ['auto', 'your-worker-id', '']:
            worker_id = auto_detect_worker_id(config_data['jira_url'], config_data['jira_pat_token'])

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
            # Lunch break configuration
            lunch_enabled=config_data.get('lunch_enabled', False),
            lunch_time=config_data.get('lunch_time', '13:00'),
            lunch_duration_minutes=config_data.get('lunch_duration_minutes', 30),
            # Sequential time allocation settings
            sequential_allocation_enabled=seq_config.get('enabled', True),
            work_start_time=seq_config.get('work_start_time', '08:00'),
            work_end_time=seq_config.get('work_end_time', '17:30'),
            gap_minutes=seq_config.get('gap_minutes', 5),
            static_tasks_priority=seq_config.get('static_tasks_priority', True)
        )

        return config

    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in config file: {e}")
    except Exception as e:
        raise ConfigurationError(f"Error loading config: {e}")


def setup_logging(config: Config) -> None:
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

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def load_window_mappings(mappings_file: str) -> list[WindowMapping]:
    """Load window mappings from JSON file"""
    try:
        with open(mappings_file, 'r') as f:
            data = json.load(f)

        mappings = []
        for mapping_data in data.get('mappings', []):
            try:
                mapping = WindowMapping(
                    name=mapping_data['name'],
                    pattern=mapping_data['pattern'],
                    jira_key=mapping_data['jira_key'],
                    description=mapping_data['description'],
                    match_type=mapping_data.get('match_type', 'both'),
                    enabled=mapping_data.get('enabled', True)
                )
                mappings.append(mapping)
            except Exception as e:
                logger.warning(f"Skipping invalid mapping '{mapping_data.get('name', 'unknown')}': {e}")

        logger.info(f"Loaded {len(mappings)} window mappings")
        return mappings

    except FileNotFoundError:
        logger.warning(f"Mappings file {mappings_file} not found")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in mappings file: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading mappings: {e}")
        return []


def load_static_tasks(static_tasks_file: str) -> list[StaticTask]:
    """Load static tasks from JSON file"""
    try:
        with open(static_tasks_file, 'r') as f:
            data = json.load(f)

        tasks = []
        
        # Load daily tasks
        for task_data in data.get('daily_tasks', []):
            try:
                task = StaticTask(
                    name=task_data['name'],
                    jira_key=task_data['jira_key'],
                    time=task_data['time'],
                    duration_minutes=task_data['duration_minutes'],
                    description=task_data['description'],
                    enabled=task_data.get('enabled', True)
                )
                tasks.append(task)
            except Exception as e:
                logger.warning(f"Skipping invalid daily task '{task_data.get('name', 'unknown')}': {e}")

        # Load weekly tasks
        for task_data in data.get('weekly_tasks', []):
            try:
                task = StaticTask(
                    name=task_data['name'],
                    jira_key=task_data['jira_key'],
                    time=task_data['time'],
                    duration_minutes=task_data['duration_minutes'],
                    description=task_data['description'],
                    enabled=task_data.get('enabled', True),
                    day_of_week=task_data.get('day_of_week')
                )
                tasks.append(task)
            except Exception as e:
                logger.warning(f"Skipping invalid weekly task '{task_data.get('name', 'unknown')}': {e}")

        logger.info(f"Loaded {len(tasks)} static tasks")
        return tasks

    except FileNotFoundError:
        logger.warning(f"Static tasks file {static_tasks_file} not found")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in static tasks file: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading static tasks: {e}")
        return [] 