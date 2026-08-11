"""Config persistence: a JSON file in the user config directory."""

import copy
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".kbl"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "workspaces": [],
    "active_workspace": None,
    "layout": "tree-editor-chat",
    "panel_sizes": {},
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    def __init__(self, path=None):
        self.path = Path(path) if path else CONFIG_FILE
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self):
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                self.data = _deep_merge(DEFAULTS, stored)
            except (json.JSONDecodeError, OSError):
                self.data = copy.deepcopy(DEFAULTS)
        return self.data

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2) + "\n", encoding="utf-8"
        )
