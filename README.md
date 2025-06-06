# ActivityWatch to Jira Tempo Automation

Automatically populate your Jira Tempo timesheets using ActivityWatch data, with intelligent activity detection and time tracking.

## Overview

This tool bridges ActivityWatch (time tracking) with Jira Tempo (timesheet management) to automate the tedious process of logging work hours. It analyzes your computer activity, extracts Jira ticket references, categorizes work types, and automatically submits time entries to Tempo.

## Features

### ✅ Automated Time Tracking

- **Jira Ticket Detection**: Automatically detects SE-prefixed tickets in window titles
- **Static Task Management**: Configurable daily/weekly recurring tasks (standup, admin, etc.)
- **Activity Categorization**: Intelligently categorizes work as Development, Meetings, Research, etc.
- **Smart Time Management**: User-controlled overflow handling with intelligent suggestions
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

- **Static Mappings**: Map specific window titles to Jira tickets (e.g., "ZScaler TAM Meet" → SE-1234)
- **Regex Patterns**: Flexible pattern matching for recurring activities
- **Custom Descriptions**: Override default descriptions with meaningful text
- **Activity Type Assignment**: Automatically categorize mapped activities

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

#### Tempo API Token

1. In Jira, go to Apps → Tempo → Settings
2. Navigate to API Integration
3. Generate new token
4. Save securely

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/TerrifiedBug/activitywatch-tempo.git
cd activitywatch-tempo
```

### 2. Setup Virtual Environment (Recommended)

Using a virtual environment is the best practice to avoid dependency conflicts:

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

The configuration file is already named `config.json` and ready to use.

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
  "preview_file_path": "tempo_preview.json",
  "default_processing_mode": "daily",
  "mappings_file": "mappings.json",
  "static_tasks_file": "static_tasks.json",
  "log_level": "DEBUG",
  "log_file": "activitywatch-tempo.log",
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

Edit `mappings.json` to map specific window titles to Jira tickets:

```json
{
  "mappings": [
    {
      "name": "ZScaler TAM Meetings",
      "pattern": "ZScaler TAM Meet",
      "jira_key": "SE-1234",
      "activity_type": "Meeting",
      "description": "ZScaler TAM vendor call"
    },
    {
      "name": "Sprint Planning",
      "pattern": "Twitch|Sprint Planning|Planning Meeting",
      "jira_key": "SE-PLANNING",
      "activity_type": "Meeting",
      "description": "Sprint planning session"
    },
    {
      "name": "Vendor Calls",
      "pattern": "Vendor Call|Partner Meeting|External Meeting",
      "jira_key": "SE-VENDOR",
      "activity_type": "Meeting",
      "description": "External vendor/partner call"
    }
  ],
  "settings": {
    "case_sensitive": false,
    "priority": "first_match",
    "fallback_to_ticket_detection": true
  }
}
```

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
      "activity_type": "Meeting",
      "enabled": true
    },
    {
      "name": "Email Review",
      "jira_key": "SE-ADMIN",
      "time": "08:30",
      "duration_minutes": 15,
      "description": "Daily email review and admin tasks",
      "activity_type": "Administration",
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
      "activity_type": "Meeting",
      "enabled": false
    }
  ]
}
```

## Running the Script

### Prerequisites Check

Before running, ensure:

- ✅ **ActivityWatch is running**: Check with `curl http://localhost:5600/api/0/buckets`
- ✅ **Virtual environment activated**: `source venv/bin/activate` (or `venv\Scripts\activate` on Windows)
- ✅ **Configuration complete**: API tokens set in `config.json`
- ✅ **Window mappings configured**: Custom mappings in `window_mappings.json`

### Running Options

#### Option A: Manual Daily/Weekly Processing (Recommended)

```bash
# Always activate virtual environment first
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Generate preview for yesterday
python activitywatch-tempo.py --preview

# Review and edit tempo_preview.json manually
# Then submit
python activitywatch-tempo.py --submit
```

#### Option B: Automated Scheduling

```bash
# Run scheduler (processes previous day at 8 AM daily)
python activitywatch-tempo.py --scheduler
```

#### Option C: Development/Testing

```bash
# Test with specific date
python activitywatch-tempo.py --preview --date 2024-01-15

# Direct processing (skip preview)
python activitywatch-tempo.py --direct --date 2024-01-15
```

### Recommended Daily Workflow

1. **Morning**: Let ActivityWatch collect data throughout your workday
2. **End of day**: Run `python activitywatch-tempo.py --preview`
3. **Review**: Edit the generated `tempo_preview.json` file to adjust time entries
4. **Submit**: Run `python activitywatch-tempo.py --submit`

## Usage

### Preview/Edit Workflow (Recommended)

The script now supports a two-stage workflow for better control:

#### Stage 1: Generate Preview

```bash
# Generate daily preview for yesterday
python activitywatch-tempo.py --preview

# Generate weekly preview for last week (Monday-Friday)
python activitywatch-tempo.py --preview --weekly

# Generate preview for specific date
python activitywatch-tempo.py --preview --date 2024-01-15

# Generate weekly preview for specific week
python activitywatch-tempo.py --preview --weekly --date 2024-01-15
```

This creates a `tempo_preview.json` file with all detected time entries that you can manually review and edit.

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
      "description": "Daily standup meeting",
      "activity_type": "Meeting"
    },
    {
      "jira_key": "SE-1234",
      "duration_seconds": 14400,
      "start_time": "2024-01-14T10:00:00",
      "description": "Work on SE-1234 (5 activities)",
      "activity_type": "Development"
    }
  ]
}
```

### Manual Editing

You can manually edit the preview file to:

- **Adjust durations**: Change `duration_seconds` values
- **Reassign tickets**: Modify `jira_key` for different ticket assignment
- **Update descriptions**: Edit `description` text
- **Change activity types**: Modify `activity_type` (Development, Meeting, Research, etc.)
- **Add entries**: Copy the entry structure to add manual entries
- **Remove entries**: Delete unwanted entries
- **Split time**: Divide long sessions across multiple tickets

#### Stage 2: Submit After Review

```bash
# Submit the reviewed entries to Tempo
python activitywatch-tempo.py --submit
```

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

### System Service Setup (Optional)

For automatic startup and background processing, you can set up the script as a system service:

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

## How It Works

### ActivityWatch Integration

The script connects to ActivityWatch through its REST API that runs locally on your machine:

#### Connection Details

- **API Endpoint**: `http://localhost:5600` (ActivityWatch's default API)
- **Data Source**: Local SQLite databases on your machine
- **Privacy**: No data leaves your machine until you choose to submit to Jira/Tempo

#### Data Retrieved

From ActivityWatch, the script gets:

- **Window titles** (e.g., "JIRA - SE-1234: Fix login bug - Chrome")
- **Application names** (e.g., "Google Chrome", "Microsoft Teams")
- **Timestamps** (when each window was active)
- **Duration** (how long each window was in focus)

#### API Calls Made

```python
# Get list of available data buckets
GET http://localhost:5600/api/0/buckets

# Get events from the window watcher bucket
GET http://localhost:5600/api/0/buckets/{bucket_name}/events?start=2024-01-14&end=2024-01-15
```

### 1. Data Collection

- ActivityWatch monitors window titles and application usage
- Data stored locally in SQLite database
- No sensitive information leaves your machine until processing

### 2. Activity Analysis

```python
# Example window title processing
"JIRA - SE-1234: Fix login bug - Chrome" → Ticket: SE-1234, Type: Development
"Microsoft Teams - SE-5678 Sprint Planning" → Ticket: SE-5678, Type: Meeting
"Daily Standup - Microsoft Teams" → Ticket: SE-STANDUP, Type: Meeting
```

### 3. Time Entry Creation

- Groups fragmented activities by Jira ticket
- Applies minimum duration filters (5 minutes default)
- Adds daily standup entry automatically
- Validates total doesn't exceed 7.5 hours

### 4. Tempo Submission

- Validates Jira tickets exist
- Submits time entries via Tempo API
- Provides detailed logging for troubleshooting

## Configuration Options

| Setting                             | Description                    | Default                 |
| ----------------------------------- | ------------------------------ | ----------------------- |
| `working_hours_per_day`             | Maximum hours per day          | 7.5                     |
| `time_rounding_minutes`             | Round time to nearest interval | 15 (15, 30, or 60)      |
| `jira_ticket_pattern`               | Regex for ticket detection     | SE-\\d+                 |
| `minimum_activity_duration_seconds` | Minimum trackable activity     | 300                     |
| `excluded_apps`                     | Apps to ignore                 | []                      |
| `default_processing_mode`           | Default mode (daily/weekly)    | daily                   |
| `mappings_file`                     | Path to window mappings config | mappings.json           |
| `static_tasks_file`                 | Path to static tasks config    | static_tasks.json       |
| `log_level`                         | Logging verbosity level        | INFO                    |
| `log_file`                          | Log file path                  | activitywatch-tempo.log |

## Workflow Examples

### Typical Daily Workflow

1. **9:30 AM**: Automatic standup entry (SE-STANDUP, 30 min)
2. **Work Sessions**: Open tickets in browser/IDE
   - "SE-1234: User authentication" → Tracked automatically
   - "SE-5678: Database optimization" → Tracked automatically
3. **Teams Meetings**:
   - With Jira ID: "SE-9999 Sprint Review" → Tracked automatically
   - Without ID: Manual linking required (future enhancement)
4. **Next Day 8:00 AM**: Previous day automatically submitted to Tempo

### Manual Teams Meeting Linking

For meetings without Jira IDs in titles:

```python
# Future enhancement - manual override
manager.add_manual_entry(
    jira_key="SE-1111",
    start_time=datetime(2024, 1, 15, 14, 0),
    duration_minutes=60,
    description="Sprint retrospective meeting"
)
```

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

#### Tempo API Errors

- Verify API token has correct permissions
- Check Jira URL format (include https://)
- Ensure tickets exist in Jira before time logging

#### Time Validation Issues

```python
# Debug time entries before submission
entries = processor.process_daily_activities(date)
for entry in entries:
    print(f"{entry.jira_key}: {entry.duration_seconds/3600:.2f}h")
```

### Logging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Recent Improvements (June 2025)

### User Control Enhancement

**Enhanced Overflow Handling**: Removed automatic proportional scaling when over daily limits. Users now have full control over time adjustments with intelligent suggestions for what to reduce.

**Smart Suggestions**: When time exceeds daily limits, the system analyzes entries and suggests specific reductions based on:

- Admin/overhead tasks that can be reduced
- Short activities that might be removed
- General/research activities that could be trimmed
- Multiple entries for the same ticket that could be consolidated

**Submission Validation**: Added validation that blocks submission when still over daily limits, requiring manual adjustment before proceeding.

### Configuration Simplification

**Removed Username Requirement**: Eliminated unnecessary `jira_username` field since PAT tokens don't require it. Configuration is now simpler and matches modern authentication practices.

**Fixed Duplicate Auto-Detection**: Resolved issue where worker ID was being auto-detected twice during initialization, eliminating duplicate log messages.

### Authentication Improvements

**Single Token Authentication**: Simplified from dual-token system to single `jira_pat_token` that handles both Jira and Tempo API access.

**Automatic Worker ID Detection**: System now auto-detects worker ID from PAT token, eliminating manual configuration in most cases.

### Bug Fixes

**Sequential Time Allocation**: Fixed critical issue where multiple tasks were assigned to the same timestamp due to time rounding happening after sequential allocation.

**Duration Filtering**: Fixed inconsistent duration filtering that prevented window mappings from working correctly when activity duration was between 60-300 seconds.

## Previous Bug Fixes

### Duration Filtering Fix (January 2025)

**Issue**: Window title mappings (like Twitch → SE-twitch) were not working when total activity duration was between 60-300 seconds, despite having `minimum_activity_duration_seconds` set to 60 in config.json.

**Root Cause**: The code had inconsistent duration filtering logic:

- Individual events were filtered using the config setting (60s) for non-mapped activities only
- Activity blocks were filtered using a hardcoded 300-second (5-minute) threshold
- This meant mapped activities would be grouped correctly but then filtered out if total duration was between 60-300 seconds

**Solution**:

- Removed early filtering of individual events during processing
- Changed hardcoded 300s threshold to use `minimum_activity_duration_seconds` from config
- Now all duration filtering uses the consistent config setting

**Result**: Window mappings now work correctly for activities with durations ≥ your configured minimum (default: 60 seconds).

## Future Enhancements

### Planned Features

- [ ] **Web UI**: Manual meeting linking interface
- [ ] **AI Categorization**: GPT-powered activity classification
- [ ] **Multiple Ticket Patterns**: Support different project prefixes
- [ ] **Time Splitting**: Distribute long sessions across multiple tickets
- [ ] **Slack Integration**: Extract Jira references from Slack messages
- [ ] **Mobile Time Tracking**: Integration with mobile time tracking apps

### AI-Powered Improvements

```python
# Future: AI-powered activity categorization
def ai_categorize_activity(window_title, app_name, context):
    """Use GPT to intelligently categorize ambiguous activities"""
    prompt = f"""
    Categorize this work activity:
    App: {app_name}
    Window: {window_title}
    Context: {context}

    Categories: Development, Meeting, Research, Documentation, Testing
    """
    # Implementation with OpenAI API
```

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
- **Discussions**: [GitHub Discussions](https://github.com/your-username/activitywatch-tempo/discussions)
- **ActivityWatch**: [Official Documentation](https://docs.activitywatch.net/)
- **Tempo API**: [Tempo REST API Documentation](https://tempo-io.github.io/tempo-api-docs/)

---

**Note**: This tool is designed for professional time tracking and requires proper API access to Jira and Tempo. Always ensure compliance with your organization's time tracking policies.
