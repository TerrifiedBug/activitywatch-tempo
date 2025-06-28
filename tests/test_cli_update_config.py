import sys
import json
import types
from pathlib import Path
import importlib

import pytest

# Stub external dependencies used by awtempo.cli
class DummyResponse:
    status_code = 200
    def json(self):
        return {"key": "dummy"}

class DummySession:
    def __init__(self):
        self.headers = {}
    def get(self, url):
        return DummyResponse()

def setup_stubs(monkeypatch):
    requests = types.ModuleType("requests")
    requests.Session = DummySession
    sys.modules["requests"] = requests
    # Minimal schedule stub
    if "schedule" not in sys.modules:
        sys.modules["schedule"] = types.ModuleType("schedule")


def test_update_config_creates_files(tmp_path, monkeypatch):
    setup_stubs(monkeypatch)

    # Reload module so stubs are used
    import awtempo.cli as cli
    importlib.reload(cli)

    # Avoid heavy processing during the test
    monkeypatch.setattr(cli.AutomationManager, "generate_preview", lambda self, mode=None, date=None: None)

    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.json"

    monkeypatch.setattr(sys, "argv", ["aw-tempo", "--update-config", "--config", str(config_path)])

    cli.main()

    assert config_path.exists()
    assert (tmp_path / "mappings.json").exists()
    assert (tmp_path / "static_tasks.json").exists()
    with open(config_path) as f:
        data = json.load(f)
    assert "jira_url" in data
