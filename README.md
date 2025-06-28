# ActivityWatch Tempo

This script converts ActivityWatch logs into Jira Tempo worklogs. It can extract Jira keys directly from window titles or apply custom mappings that match on window titles or application names. Activities are grouped by ticket and optional recurring tasks are added before everything is submitted to Tempo.

## Requirements

- **Python 3.7+**
- **ActivityWatch** running locally
- A Jira account with Tempo access and a Personal Access Token (PAT)

## Installation

The package on PyPI is named `awtempo`, but it installs the command-line tool
`aw-tempo`. A quick way to get started is:

```bash
pip install awtempo
aw-tempo --update-config
```

This will install the latest published version and create the default
configuration files if they don't already exist.

To install the very latest development version from GitHub run:
```bash
pip install git+https://github.com/TerrifiedBug/activitywatch-tempo.git
```

Alternatively clone the repo and install locally. `pip install .` requires
commit `85150cc` or later:
```bash
git clone https://github.com/TerrifiedBug/activitywatch-tempo.git
cd activitywatch-tempo
pip install .
```
Older commits prior to `85150cc` do not include `pyproject.toml` and cannot be
installed with `pip`.

## Configuration

After installation run:

```bash
aw-tempo --update-config
```

This command creates `config.json`, `mappings.json` and `static_tasks.json` in
the current directory if they don’t exist, or merges any new keys into existing
files. Then edit them to fit your environment. At minimum set your Jira URL and
PAT token in `config.json`.

The default templates for these configuration files are bundled with the
package under `awtempo/defaults` and copied over when running
`--update-config`.


`config.json` also controls time rounding, daily hour limits and other
behaviour.

### Mappings

`mappings.json` contains a list of rules that search window titles or
application names for patterns. Each entry includes a `pattern`, the
`jira_key` it should map to and a `match_type` (`title`, `app` or `both`). Add
new objects to the `mappings` array to automatically assign activity to a
ticket even when the key is not present in the title.

### Static tasks

`static_tasks.json` defines recurring tasks that are inserted automatically.
Daily tasks go in the `daily_tasks` list, while weekly tasks live under
`weekly_tasks` and include a `day_of_week` field. Each task needs a `time`,
`duration_minutes`, target `jira_key` and description.

## Basic Usage

Generate a preview of yesterday's entries (recommended):
```bash
aw-tempo
```
Review the `tempo_preview.json` file and edit it if needed, then submit:
```bash
aw-tempo --submit
```

### Additional Options

- `--weekly` – process a whole week (Monday–Friday)
- `--date YYYY-MM-DD` – process a specific date
- `--direct` – process and submit without creating a preview (not recommended)
- `--scheduler` – run a daily scheduler that processes the previous day at 08:00
- `--config PATH` – use an alternative configuration file
- `--update-config` – merge new default settings into your config files

## Preview File

The preview file contains all detected time entries with start times, durations and comments. You can adjust anything in this file before submitting to Tempo.

## Example Workflow

1. Ensure ActivityWatch is running.
2. At the end of the day run `aw-tempo`.
3. Open `tempo_preview.json`, tweak times or ticket keys if necessary.
4. Submit with `aw-tempo --submit`.

## Logging

Logs are written to the file specified by `log_file` in `config.json` (default: `activitywatch-tempo.log`). Set `log_level` to `DEBUG` for more verbose output.

## Notes

Each ActivityWatch event is first compared against your mappings. If no mapping
matches, the script falls back to detecting Jira issue keys directly from the
window title using `jira_ticket_pattern` (default `SE-123`). Adjust the pattern
if your project uses a different prefix.

## License

This project is licensed under the [MIT License](LICENSE).
