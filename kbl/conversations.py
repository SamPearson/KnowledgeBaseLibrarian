"""Conversation store: persistent chat conversations on disk.

Each conversation is a JSON file named <id>.json. Conversations are
scoped per workspace: files live in a subfolder ``conversations/<workspace-id>``
keyed by a stable hash of the workspace path. When no workspace is open,
files live directly in the conversations directory. Conversations are
addressed by name in the UI and by id in files and the config.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

from kbl.config import CONFIG_DIR

CONVERSATIONS_DIR = CONFIG_DIR / "conversations"


def workspace_id_for(workspace_path):
    """Stable id for a workspace folder: a short sha256 of its path."""
    if not workspace_path:
        return None
    path = str(Path(workspace_path)).rstrip("/")
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


class ConversationStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else CONVERSATIONS_DIR

    def _scope_dir(self, workspace_id):
        if workspace_id:
            return self.directory / workspace_id
        return self.directory

    def _path(self, conv_id, workspace_id):
        return self._scope_dir(workspace_id) / f"{conv_id}.json"

    def list_conversations(self, workspace_id=None):
        """Return [{id, name, updated_at}] sorted by most recent first."""
        scope = self._scope_dir(workspace_id)
        if not scope.exists():
            return []
        results = []
        for path in scope.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(data, dict) or not data.get("id"):
                continue
            results.append(
                {
                    "id": str(data["id"]),
                    "name": str(data.get("name") or data["id"]),
                    "updated_at": data.get("updated_at") or 0.0,
                }
            )
        results.sort(key=lambda c: c["updated_at"], reverse=True)
        return results

    def save(self, conversation, workspace_id=None):
        """Persist a conversation dict, assigning an id if missing.

        Returns the conversation id.
        """
        if not conversation.get("id"):
            conversation["id"] = uuid.uuid4().hex
        now = time.time()
        conversation["updated_at"] = now
        if not conversation.get("created_at"):
            conversation["created_at"] = now
        self._scope_dir(workspace_id).mkdir(parents=True, exist_ok=True)
        self._path(conversation["id"], workspace_id).write_text(
            json.dumps(conversation, indent=2) + "\n", encoding="utf-8"
        )
        return conversation["id"]

    def load(self, conv_id, workspace_id=None):
        try:
            data = json.loads(
                self._path(conv_id, workspace_id).read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        data.setdefault("messages", [])
        return data

    def rename(self, conv_id, name, workspace_id=None):
        data = self.load(conv_id, workspace_id)
        if data is None:
            return False
        data["name"] = name
        self.save(data, workspace_id)
        return True

    def name_exists(self, name, workspace_id=None):
        return any(c["name"] == name for c in self.list_conversations(workspace_id))

    def find_by_name(self, name, workspace_id=None):
        for conv in self.list_conversations(workspace_id):
            if conv["name"] == name:
                return conv
        return None
