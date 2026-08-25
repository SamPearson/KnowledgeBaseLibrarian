"""Config persistence: a JSON file in the user config directory."""

import copy
import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".kbl"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Cache for the default-path Config so every ``Config()`` call within a process
# returns the same live instance. Tools executed inside the running app call
# ``Config()`` and must observe the same in-memory state as the application,
# including the per-instance ``active_workspace``, which is held in memory and
# never written to the shared config file.
_DEFAULT_INSTANCE = None

DEFAULTS = {
    "workspaces": [],
    "default_workspace": None,
    "layout": "tree-editor-chat",
    "panel_sizes": {},
    "active_theme": "dark",
    "server": "",
    "model": "",
    "api_key": "",
    "active_agent": None,
    "disabled_tools": [],
    "active_conversation": {},
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
    def __new__(cls, path=None):
        # The default config is a process-wide singleton: tools executed inside
        # the running app call Config() and must see the same in-memory state
        # (including the per-instance active_workspace) as the application.
        if path is None:
            global _DEFAULT_INSTANCE
            if _DEFAULT_INSTANCE is None:
                _DEFAULT_INSTANCE = super().__new__(cls)
            return _DEFAULT_INSTANCE
        return super().__new__(cls)

    def __init__(self, path=None):
        if getattr(self, "_initialized", False):
            return
        self.path = Path(path) if path else CONFIG_FILE
        self.data = copy.deepcopy(DEFAULTS)
        self.active_workspace = None
        self.load()
        self._initialized = True

    def load(self):
        if self.path.exists():
            try:
                stored = json.loads(self.path.read_text(encoding="utf-8"))
                self.data = _deep_merge(DEFAULTS, stored)
            except (json.JSONDecodeError, OSError):
                self.data = copy.deepcopy(DEFAULTS)
        if self.data.get("active_theme") == "default":
            # Migrate the legacy name of the builtin dark theme.
            self.data["active_theme"] = "dark"
        if isinstance(self.data.get("active_theme"), str):
            # Strip accidental whitespace from persisted theme names.
            self.data["active_theme"] = self.data["active_theme"].strip()
        # Migrate the legacy single shared "active_workspace" into the
        # per-instance "default_workspace". The active workspace is now
        # per-instance session state and must never be persisted to the
        # shared config file, so two running instances cannot operate on
        # each other's project.
        if "active_workspace" in self.data:
            if self.data.get("default_workspace") is None:
                self.data["default_workspace"] = self.data["active_workspace"]
            del self.data["active_workspace"]
        if isinstance(self.data.get("active_conversation"), str):
            # Migrate the legacy single conversation id to a per-workspace map.
            from kbl.conversations import workspace_id_for

            conv_id = self.data["active_conversation"]
            self.data["active_conversation"] = {
                workspace_id_for(self.data.get("default_workspace")): conv_id
            }
        return self.data

    def save(self, merge=True):
        data = self.data
        if merge and self.path.exists():
            # Merge shared collection keys with whatever is currently on disk so
            # that a save from this instance never clobbers data owned by
            # another concurrently-running instance (e.g. a workspace the other
            # instance registered, or that instance's per-workspace conversation
            # selection). Single-value settings remain last-save-wins.
            try:
                disk = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                disk = {}
            if isinstance(disk, dict):
                merged = copy.deepcopy(data)
                disk_ws = {str(Path(p)) for p in disk.get("workspaces", [])}
                self_ws = {str(Path(p)) for p in data.get("workspaces", [])}
                merged["workspaces"] = sorted(disk_ws | self_ws)
                merged_ac = dict(disk.get("active_conversation", {}))
                merged_ac.update(data.get("active_conversation", {}))
                merged["active_conversation"] = merged_ac
                data = merged
        # active_workspace is per-instance session state; never persist it.
        data = {k: v for k, v in data.items() if k != "active_workspace"}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        self.data = data