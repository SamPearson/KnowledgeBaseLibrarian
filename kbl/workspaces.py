"""Workspace management: a user-managed list of top-level folders.

A workspace is a folder on disk whose markdown files form a knowledge base.
The app keeps a list of known workspaces and one active workspace.
"""

from pathlib import Path


class WorkspaceManager:
    def __init__(self, config):
        self.config = config

    @property
    def workspaces(self):
        return [Path(p) for p in self.config.data["workspaces"]]

    def add(self, path):
        path = Path(path).expanduser()
        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")
        entries = self.config.data["workspaces"]
        if str(path) not in entries:
            entries.append(str(path))
            self.config.save()
        if not self.config.data.get("active_workspace"):
            self.set_active(path)
        return path

    def remove(self, path):
        path = Path(path)
        key = str(path)
        entries = self.config.data["workspaces"]
        if key in entries:
            entries.remove(key)
        if self.config.data.get("active_workspace") == key:
            self.config.data["active_workspace"] = entries[0] if entries else None
        self.config.save()

    def set_active(self, path):
        path = Path(path)
        entries = self.config.data["workspaces"]
        if str(path) not in entries:
            if not path.is_dir():
                raise ValueError(f"Not a directory: {path}")
            entries.append(str(path))
        self.config.data["active_workspace"] = str(path)
        self.config.save()

    @property
    def active(self):
        active = self.config.data.get("active_workspace")
        if active:
            path = Path(active)
            if path.is_dir():
                return path
        return None
