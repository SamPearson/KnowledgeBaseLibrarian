"""Workspace management: a user-managed list of top-level folders.

A workspace is a folder on disk whose markdown files form a knowledge base.
The app keeps a list of known workspaces and one active workspace per
instance. The active workspace is per-instance session state: it is never
persisted to the shared config file, so multiple running instances cannot
operate on each other's project.
"""

from pathlib import Path

from kbl.conversations import workspace_id_for


class WorkspaceManager:
    def __init__(self, config):
        self.config = config

    @property
    def workspaces(self):
        return [Path(p) for p in self.config.data["workspaces"]]

    def register(self, path):
        """Make ``path`` known to this instance. Idempotent and safe to call at
        launch (e.g. via --workspace). Sets the per-instance active workspace
        but does NOT change the persisted default workspace."""
        p = str(Path(path).expanduser())
        entries = self.config.data["workspaces"]
        if p not in entries:
            entries.append(p)
            self.config.save()
        self.config.active_workspace = p
        return Path(p)

    def add(self, path):
        path = Path(path).expanduser()
        if not path.is_dir():
            raise ValueError(f"Not a directory: {path}")
        p = str(path)
        if p in self.config.data["workspaces"]:
            raise ValueError(f"Workspace already added: {p}")
        self.config.data["workspaces"].append(p)
        self.config.save()
        self.config.active_workspace = p
        return path

    def remove(self, path):
        key = str(Path(path).expanduser())
        entries = self.config.data["workspaces"]
        if key in entries:
            entries.remove(key)
        if self.config.active_workspace == key:
            self.config.active_workspace = None
        if self.config.data.get("default_workspace") == key:
            self.config.data["default_workspace"] = None
        self.config.data.setdefault("active_conversation", {}).pop(
            workspace_id_for(key), None
        )
        # Raw write (merge=False) so the merge-union in Config.save cannot
        # resurrect the just-removed workspace from other on-disk state.
        self.config.save(merge=False)

    def set_active(self, path, persist_default=False):
        p = str(Path(path).expanduser())
        self.config.active_workspace = p
        if persist_default:
            self.config.data["default_workspace"] = p
            self.config.save()

    @property
    def active(self):
        aw = self.config.active_workspace
        if aw:
            path = Path(aw)
            if path.is_dir():
                return path
        dw = self.config.data.get("default_workspace")
        if dw:
            path = Path(dw)
            if path.is_dir():
                return path
        return None
