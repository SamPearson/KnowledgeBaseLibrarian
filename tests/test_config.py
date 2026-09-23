"""Tests for kbl.config: defaults, persistence, singleton, migrations, merge."""

import json

import pytest

from kbl import config
from kbl.conversations import workspace_id_for


def test_defaults_on_missing_file(tmp_path):
    cfg = config.Config(path=str(tmp_path / "config.json"))
    assert cfg.data["layout"] == "tree-editor-chat"
    assert cfg.data["active_theme"] == "dark"
    assert cfg.data["max_tool_rounds"] == 8
    assert cfg.data["workspaces"] == []


def test_save_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = config.Config(path=str(path))
    cfg.data["model"] = "qwen3"
    cfg.data["max_tool_rounds"] = 12
    cfg.save()
    loaded = config.Config(path=str(path))
    assert loaded.data["model"] == "qwen3"
    assert loaded.data["max_tool_rounds"] == 12


def test_save_never_persists_active_workspace(tmp_path):
    path = tmp_path / "config.json"
    cfg = config.Config(path=str(path))
    cfg.active_workspace = str(tmp_path / "ws")
    cfg.save()
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert "active_workspace" not in disk


def test_save_merges_workspaces_across_instances(tmp_path):
    path = tmp_path / "config.json"
    a = config.Config(path=str(path))
    b = config.Config(path=str(path))
    a.data["workspaces"] = ["/x"]
    a.save()
    b.data["workspaces"] = ["/y"]
    b.save()
    assert set(config.Config(path=str(path)).data["workspaces"]) == {"/x", "/y"}


def test_save_merges_active_conversation_across_instances(tmp_path):
    path = tmp_path / "config.json"
    a = config.Config(path=str(path))
    b = config.Config(path=str(path))
    a.data["active_conversation"] = {"ws1": "conv1"}
    a.save()
    b.data["active_conversation"] = {"ws2": "conv2"}
    b.save()
    ac = config.Config(path=str(path)).data["active_conversation"]
    assert ac == {"ws1": "conv1", "ws2": "conv2"}


def test_save_merge_false_overwrites(tmp_path):
    path = tmp_path / "config.json"
    a = config.Config(path=str(path))
    b = config.Config(path=str(path))
    a.data["workspaces"] = ["/x"]
    a.save()
    b.data["workspaces"] = []
    b.save(merge=False)
    assert config.Config(path=str(path)).data["workspaces"] == []


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    cfg = config.Config(path=str(path))
    assert cfg.data["layout"] == "tree-editor-chat"


def test_migrate_theme_default_to_dark(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"active_theme": "default"}))
    assert config.Config(path=str(path)).data["active_theme"] == "dark"


def test_migrate_theme_strips_whitespace(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"active_theme": "  gruvbox  "}))
    assert config.Config(path=str(path)).data["active_theme"] == "gruvbox"


def test_migrate_active_workspace_to_default_workspace(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"active_workspace": "/legacy/ws"}))
    cfg = config.Config(path=str(path))
    assert cfg.data["default_workspace"] == "/legacy/ws"
    assert "active_workspace" not in cfg.data


def test_migrate_string_active_conversation_to_map(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"default_workspace": "/ws", "active_conversation": "abc123"})
    )
    cfg = config.Config(path=str(path))
    assert cfg.data["active_conversation"] == {
        workspace_id_for("/ws"): "abc123"
    }


def test_default_config_is_singleton(tmp_path):
    a = config.Config()
    b = config.Config()
    assert a is b
    assert a.path == config.CONFIG_FILE


def test_default_instance_isolated_from_path_instances(tmp_path):
    default = config.Config()
    explicit = config.Config(path=str(tmp_path / "other.json"))
    assert default is not explicit


def test_deep_merge_nested():
    base = {"a": {"b": 1, "c": 2}}
    override = {"a": {"b": 99}}
    assert config._deep_merge(base, override) == {"a": {"b": 99, "c": 2}}