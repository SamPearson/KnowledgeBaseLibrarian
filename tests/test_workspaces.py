"""Tests for kbl.workspaces: WorkspaceManager around the config store."""

import pytest

from kbl.workspaces import WorkspaceManager
from kbl.conversations import workspace_id_for


def test_register_sets_active_and_saves(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    returned = mgr.register(str(ws))
    assert returned == ws
    assert str(ws) in tmp_config.data["workspaces"]
    assert tmp_config.active_workspace == str(ws)


def test_register_is_idempotent(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.register(str(ws))
    mgr.register(str(ws))
    assert tmp_config.data["workspaces"].count(str(ws)) == 1


def test_add_requires_directory(tmp_config, tmp_path):
    missing = tmp_path / "nope"
    mgr = WorkspaceManager(tmp_config)
    with pytest.raises(ValueError, match="Not a directory"):
        mgr.add(str(missing))


def test_add_duplicate_raises(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.add(str(ws))
    with pytest.raises(ValueError, match="already added"):
        mgr.add(str(ws))


def test_remove_clears_active_and_default(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.register(str(ws))
    tmp_config.data["default_workspace"] = str(ws)
    tmp_config.data.setdefault("active_conversation", {})[
        workspace_id_for(str(ws))
    ] = "conv1"
    tmp_config.save()
    mgr.remove(str(ws))
    assert str(ws) not in tmp_config.data["workspaces"]
    assert tmp_config.active_workspace is None
    assert tmp_config.data["default_workspace"] is None
    assert tmp_config.data["active_conversation"] == {}


def test_remove_writes_merge_false(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.add(str(ws))
    mgr.remove(str(ws))
    assert tmp_config.data["workspaces"] == []


def test_set_active_no_persist_by_default(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.set_active(str(ws))
    assert tmp_config.active_workspace == str(ws)
    assert tmp_config.data["default_workspace"] is None


def test_set_active_persist_default(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    mgr.set_active(str(ws), persist_default=True)
    assert tmp_config.data["default_workspace"] == str(ws)


def test_active_falls_back_to_default(tmp_config, tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mgr = WorkspaceManager(tmp_config)
    tmp_config.data["default_workspace"] = str(ws)
    assert mgr.active == ws


def test_active_none_when_not_a_directory(tmp_config, tmp_path):
    mgr = WorkspaceManager(tmp_config)
    tmp_config.data["default_workspace"] = str(tmp_path / "missing")
    assert mgr.active is None