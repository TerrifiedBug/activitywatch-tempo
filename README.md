# ActivityWatch to Jira Tempo Automation

Automatically populate your Jira Tempo timesheets using ActivityWatch data, with intelligent activity detection and time tracking.

## Overview

This tool bridges ActivityWatch (time tracking) with Jira Tempo (timesheet management) to automate the tedious process of logging work hours. It analyzes your computer activity, extracts Jira ticket references, and automatically submits time entries to Tempo.

## Features

### ✅ Automated Time Tracking

- **Jira Ticket Detection**: Automatically detects SE-prefixed tickets in window titles
- **Static Task Management**: Configurable daily/weekly recurring tasks (standup, admin, etc.)
- **Smart Time Management**: User-controlled overflow handling with detailed reporting
- **Automatic Worker ID Detection**: Auto-detects worker ID from PAT token

### ✅ Smart Activity Processing

- **Window Title Analysis**: Extracts Jira tickets from browser tabs, IDE windows, etc.
- **Application-Based Categorization**: Different handling for IDEs, browsers, meeting apps
- **Activity Grouping**: Consolidates fragmented work sessions on the same ticket
- **Configurable Duration Filtering**: Uses consistent minimum duration threshold from config (default: 60 seconds)

### ✅ Teams Meeting Integration

- **Automatic Detection**: Identifies Teams meetings with Jira IDs in titles
- **Manual Linking Support**: Framework for linking meetings without Jira references
- **Meeting Categorization**: Distinguishes between standups and regular meetings

### ✅ Window Title Mappings

- **Flexible Pattern Matching**: Map specific window titles or app names to Jira tickets
- **Individual Control**: Enable/disable each mapping independently
- **Match Types**: Target window titles, app names, or both
- **Custom Descriptions**: Override default descriptions with meaningful text

### ✅ Lunch Break Support

- **Configurable Lunch Breaks**: Set lunch time and duration to block time slots
- **No Jira Entries**: Lunch breaks don't create time entries (as Tempo expects)
- **Seamless Integration**: Works with sequential time allocation

### ✅ Robust Integration

- **Jira Validation**: Verifies ticket existence before time submission
- **Error Handling**: Comprehensive logging and graceful failure handling
- **Flexible Scheduling**: Daily automation with manual override options

## Prerequisites

### Required Software

1. **ActivityWatch**: Install from [activitywatch.net](https://activitywatch.net/)
2. **Python 3.7+**: Required for the automation script
3. **Jira/Tempo Access**: Valid API tokens for both services

### ActivityWatch Setup

```bash
# Install ActivityWatch
# Download from https://github.com/ActivityWatch/activitywatch/releases
# Or install via package manager (varies by OS)

# Start ActivityWatch
aw-server &
aw-watcher-window &
aw-watcher-afk &
```

### API Token Setup

#### Jira API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create API token
3. Save securely

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/TerrifiedBug/activitywatch-tempo.git
cd activitywatch-tempo
```

### 2. Setup Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Create Configuration

Edit `config.json` with your details:

```json
{
  "jira_url": "https://your-company.atlassian.net",
  "jira_pat_token": "your-jira-pat-token",
  "worker_id": "auto",
  "working_hours_per_day": 8.0,
  "jira_ticket_pattern": "SE-\\d+",
  "excluded_apps": ["Slack", "Personal Browser"],
  "minimum_activity_duration_seconds": 60,
  "time_rounding_minutes": 30,
  "lunch_enabled": false,
  "lunch_time": "13:00",
  "lunch_duration_minutes": 30,
  "sequential_time_allocation": {
    "enabled": true,
    "work_start_time": "08:30",
    "work_end_time": "17:00",
    "gap_minutes": 0,
    "static_tasks_priority": true
  }
}
```

### 4. Configure Window Mappings

Edit `mappings.json` to map specific window titles or apps to Jira tickets:

```json
{
  "mappings": [
    {
      "name": "ZScaler TAM Meetings",
      "pattern": "ZScaler TAM Meet",
      "jira_key": "SE-1234",
      "description": "ZScaler TAM vendor call",
      "match_type": "title",
      "enabled": true
    },
    {
      "name": "Twitch App Usage",
      "pattern": "Twitch",
      "jira_key": "SE-twitch",
      "description": "Twitch streaming activities",
      "match_type": "app",
      "enabled": true
    },
    {
      "name": "Visual Studio Code",
      "pattern": "Visual Studio Code|Code",
      "jira_key": "SE-DEVELOPMENT",
      "description": "Development work in VS Code",
      "match_type": "app",
      "enabled": false
    }
  ]
}
```

**Match Types:**

- `"title"` - Match only window titles
- `"app"` - Match only application names
- `"both"` - Match either (default)

### 5. Configure Static Tasks

Edit `static_tasks.json` to define daily and weekly recurring tasks:

```json
{
  "daily_tasks": [
    {
      "name": "Daily Standup",
      "jira_key": "SE-STANDUP",
      "time": "09:30",
      "duration_minutes": 60,
      "description": "Daily standup meeting",
      "enabled": true
    },
    {
      "name": "Email Review",
      "jira_key": "SE-ADMIN",
      "time": "08:30",
      "duration_minutes": 15,
      "description": "Daily email review and admin tasks",
      "enabled": false
    }
  ],
  "weekly_tasks": [
    {
      "name": "Sprint Planning",
      "jira_key": "SE-PLANNING",
      "day_of_week": "monday",
      "time": "10:00",
      "duration_minutes": 120,
      "description": "Weekly sprint planning session",
      "enabled": false
    }
  ]
}
```

## Usage

### Recommended Daily Workflow

1. **Morning**: Let ActivityWatch collect data throughout your workday
2. **End of day**: Run `python activitywatch-tempo.py --preview`
3. **Review**: Edit the generated `tempo_preview.json` file to adjust time entries
4. **Submit**: Run `python activitywatch-tempo.py --submit`

### Preview/Edit Workflow (Recommended)

#### Stage 1: Generate Preview

```bash
# Always activate virtual environment first
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Generate daily preview for yesterday
python activitywatch-tempo.py --preview

# Generate weekly preview for last week (Monday-Friday)
python activitywatch-tempo.py --preview --weekly

# Generate preview for specific date
python activitywatch-tempo.py --preview --date 2024-01-15
```

This creates a `tempo_preview.json` file with all detected time entries that you can manually review and edit.

#### Stage 2: Submit After Review

```bash
# Submit the reviewed entries to Tempo
python activitywatch-tempo.py --submit
```

### Preview File Format

The generated preview file contains:

```json
{
  "generated_date": "2024-01-15T10:30:00Z",
  "processing_period": {
    "start_date": "2024-01-14",
    "end_date": "2024-01-14",
    "mode": "daily"
  },
  "total_hours": 7.5,
  "entries": [
    {
      "jira_key": "SE-STANDUP",
      "duration_seconds": 1800,
      "start_time": "2024-01-14T09:30:00",
      "comment": "Daily standup meeting"
    },
    {
      "jira_key": "SE-1234",
      "duration_seconds": 14400,
      "start_time": "2024-01-14T10:00:00",
      "comment": "Work on SE-1234 (5 activities)"
    }
  ]
}
```

### Manual Editing

You can manually edit the preview file to:

- **Adjust durations**: Change `duration_seconds` values
- **Reassign tickets**: Modify `jira_key` for different ticket assignment
- **Update descriptions**: Edit `comment` text
- **Add entries**: Copy the entry structure to add manual entries
- **Remove entries**: Delete unwanted entries
- **Split time**: Divide long sessions across multiple tickets

### Direct Processing (Legacy Mode)

For immediate submission without preview:

```bash
# Process yesterday directly
python activitywatch-tempo.py --direct

# Process specific date directly
python activitywatch-tempo.py --direct --date 2024-01-15

# Process last week directly
python activitywatch-tempo.py --direct --weekly
```

### Automated Scheduling

```bash
# Start the automated scheduler (processes previous day at 8 AM)
python activitywatch-tempo.py --scheduler
```

## How It Works

### Data Collection

- ActivityWatch monitors window titles and application usage
- Data stored locally in SQLite database
- No sensitive information leaves your machine until processing

### Activity Analysis

```python
# Example window title processing
"JIRA - SE-1234: Fix login bug - Chrome" → Ticket: SE-1234
"Microsoft Teams - SE-5678 Sprint Planning" → Ticket: SE-5678
"Daily Standup - Microsoft Teams" → Mapped to SE-STANDUP
```

### Time Entry Creation

- Groups fragmented activities by Jira ticket
- Applies minimum duration filters (60 seconds default)
- Adds static tasks automatically
- Validates total doesn't exceed daily working hours

### Tempo Submission

- Validates Jira tickets exist
- Submits time entries via Tempo API
- Provides detailed logging for troubleshooting

## Configuration Options

| Setting                             | Description                    | Default            |
| ----------------------------------- | ------------------------------ | ------------------ |
| `working_hours_per_day`             | Maximum hours per day          | 7.5                |
| `time_rounding_minutes`             | Round time up to next interval | 15 (15, 30, or 60) |
| `jira_ticket_pattern`               | Regex for ticket detection     | SE-\\d+            |
| `minimum_activity_duration_seconds` | Minimum trackable activity     | 60                 |
| `excluded_apps`                     | Apps to ignore                 | []                 |
| `lunch_enabled`                     | Enable lunch break blocking    | false              |
| `lunch_time`                        | Lunch start time (HH:MM)       | 13:00              |
| `lunch_duration_minutes`            | Lunch duration in minutes      | 30                 |
| `log_level`                         | Logging verbosity level        | INFO               |

## Troubleshooting

### Common Issues

#### ActivityWatch Not Running

```bash
# Check if ActivityWatch is running
curl http://localhost:5600/api/0/buckets

# Start if needed
aw-server &
aw-watcher-window &
```

#### No Jira Tickets Detected

- Ensure window titles contain "SE-" pattern
- Check `jira_ticket_pattern` in config
- Verify ActivityWatch is collecting window data
- Check if window mappings are enabled

#### Tempo API Errors

- Verify API token has correct permissions
- Check Jira URL format (include https://)
- Ensure tickets exist in Jira before time logging

#### Time Validation Issues

- Check if total time exceeds daily working hours
- Review overflow warnings in logs
- Edit preview file to adjust time entries

### Logging

The script logs to `activitywatch-tempo.log` by default. Set `log_level` to `DEBUG` in config for detailed troubleshooting information.

## System Service Setup (Optional)

For automatic startup and background processing:

#### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task → "ActivityWatch Tempo"
3. Trigger: Daily at startup or specific time
4. Action: Start a program
5. Program: `C:\path\to\venv\Scripts\python.exe`
6. Arguments: `C:\path\to\activitywatch-tempo.py --scheduler`

#### macOS (launchd)

Create `~/Library/LaunchAgents/com.activitywatch.tempo.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.activitywatch.tempo</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>/path/to/activitywatch-tempo.py</string>
        <string>--scheduler</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

Load with: `launchctl load ~/Library/LaunchAgents/com.activitywatch.tempo.plist`

#### Linux (systemd)

Create `/etc/systemd/system/activitywatch-tempo.service`:

```ini
[Unit]
Description=ActivityWatch Tempo Integration
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/activitywatch-tempo
ExecStart=/path/to/venv/bin/python activitywatch-tempo.py --scheduler
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable with: `sudo systemctl enable activitywatch-tempo && sudo systemctl start activitywatch-tempo`

## Security Considerations

- **API Tokens**: Store securely, never commit to version control
- **Local Data**: ActivityWatch data stays on your machine
- **Network Traffic**: Only Jira/Tempo API calls leave your network
- **Permissions**: Use least-privilege API tokens

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

MIT License - see LICENSE file for details

## Support

- **Issues**: [GitHub Issues](https://github.com/your-username/activitywatch-tempo/issues)
- **ActivityWatch**: [Official Documentation](https://docs.activitywatch.net/)
- **Tempo API**: [Tempo REST API Documentation](https://tempo-io.github.io/tempo-api-docs/)

---

**Note**: This tool is designed for professional time tracking and requires proper API access to Jira and Tempo. Always ensure compliance with your organization's time tracking policies.
