"""Tests for kbl.conversations: persistent chat conversations on disk."""

import json

import pytest

from kbl import conversations


def test_workspace_id_for_stable_and_unique(tmp_path):
    a = conversations.workspace_id_for(str(tmp_path / "one"))
    b = conversations.workspace_id_for(str(tmp_path / "one"))
    c = conversations.workspace_id_for(str(tmp_path / "two"))
    assert a == b
    assert a != c
    assert len(a) == 12


def test_workspace_id_for_none():
    assert conversations.workspace_id_for(None) is None
    assert conversations.workspace_id_for("") is None


def test_save_assigns_id_and_stamps(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    conv = {"name": "hello"}
    conv_id = store.save(conv)
    assert conv["id"] == conv_id
    assert conv["updated_at"]
    assert conv["created_at"] == conv["updated_at"]
    assert (tmp_path / "conv" / f"{conv_id}.json").exists()


def test_roundtrip(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    conv_id = store.save({"name": "a", "messages": [{"role": "user", "content": "hi"}]})
    loaded = store.load(conv_id)
    assert loaded["name"] == "a"
    assert loaded["messages"] == [{"role": "user", "content": "hi"}]


def test_load_missing_returns_none(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    assert store.load("nope") is None


def test_load_corrupt_returns_none(tmp_path):
    d = tmp_path / "conv"
    d.mkdir()
    (d / "bad.json").write_text("{not json")
    store = conversations.ConversationStore(d)
    assert store.load("bad") is None


def test_list_conversations_sorted_and_skips_corrupt(tmp_path):
    d = tmp_path / "conv"
    d.mkdir()
    store = conversations.ConversationStore(d)
    first = store.save({"name": "old"})
    (d / "bad.json").write_text("{corrupt")
    second = store.save({"name": "new"})
    listed = store.list_conversations()
    assert [c["name"] for c in listed] == ["new", "old"]
    assert listed[0]["id"] == second
    assert listed[1]["id"] == first


def test_rename(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    conv_id = store.save({"name": "a"})
    assert store.rename(conv_id, "b")
    assert store.load(conv_id)["name"] == "b"
    assert not store.rename("missing", "b")


def test_name_exists_and_find(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    store.save({"name": "unique name"})
    assert store.name_exists("unique name")
    assert not store.name_exists("other")
    found = store.find_by_name("unique name")
    assert found["name"] == "unique name"
    assert store.find_by_name("other") is None


def test_workspace_scoping(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    ws_a = conversations.workspace_id_for(str(tmp_path / "a"))
    ws_b = conversations.workspace_id_for(str(tmp_path / "b"))
    id_a = store.save({"name": "same"}, ws_a)
    id_b = store.save({"name": "same"}, ws_b)
    assert ws_a != ws_b
    listed_a = store.list_conversations(ws_a)
    listed_b = store.list_conversations(ws_b)
    assert [c["id"] for c in listed_a] == [id_a]
    assert [c["id"] for c in listed_b] == [id_b]
    assert store.load(id_a, ws_a)["name"] == "same"
    assert store.load(id_b, ws_a) is None


def test_list_conversations_missing_scope_returns_empty(tmp_path):
    store = conversations.ConversationStore(tmp_path / "conv")
    assert store.list_conversations(conversations.workspace_id_for("/nope")) == []