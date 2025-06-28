# ActivityWatch Tempo

This script converts ActivityWatch logs into Jira Tempo worklogs. It scans window titles for Jira issue keys, groups your activity by ticket and optionally adds recurring tasks before submitting everything to Tempo.

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
behaviour. `mappings.json` lets you map specific window titles or applications
to Jira keys, while `static_tasks.json` defines recurring tasks like stand‑ups.

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

The script assumes window titles contain Jira issue keys (default pattern `SE-123`). Configure `jira_ticket_pattern` if your project uses a different prefix.

## License

This project is licensed under the [MIT License](LICENSE).
