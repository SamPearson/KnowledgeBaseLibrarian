"""Shared fixtures for the pure-service test suite.

Every test runs against an isolated config directory under pytest's tmp_path.
The process-wide default Config singleton (_DEFAULT_INSTANCE) is reset before
each test so a real ``Config()`` call can never touch ~/.kbl/config.json.
"""

import pytest

from kbl import config


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    config._DEFAULT_INSTANCE = None
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / ".kbl")
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / ".kbl" / "config.json")


@pytest.fixture
def kbl_dirs(monkeypatch, tmp_path):
    """Point agents/conversations storage at isolated temp dirs."""
    from kbl import agents, conversations

    agents_dir = tmp_path / ".kbl" / "agents"
    conversations_dir = tmp_path / ".kbl" / "conversations"
    monkeypatch.setattr(agents, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(conversations, "CONVERSATIONS_DIR", conversations_dir)
    return agents_dir, conversations_dir


@pytest.fixture
def tmp_config(tmp_path):
    """A Config backed by a fresh temp JSON file; does not touch the default path."""
    cfg = config.Config(path=str(tmp_path / "config.json"))
    cfg.save()
    return cfg


@pytest.fixture
def workspace(tmp_path):
    """A markdown wiki: files, a subfolder, non-md and hidden files, a tools dir."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.md").write_text("# A\nHello world\n", encoding="utf-8")
    (ws / "sub").mkdir()
    (ws / "sub" / "b.md").write_text("## B\nfoo bar\n", encoding="utf-8")
    (ws / "notes.txt").write_text("ignored", encoding="utf-8")
    (ws / ".hidden.md").write_text("hidden", encoding="utf-8")
    (ws / "tools").mkdir()
    (ws / "tools" / "secret.md").write_text("tool content", encoding="utf-8")
    return ws