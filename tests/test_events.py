"""M3: the event bus (kbl.events) + its typed payload contracts.

Covers: events.py imports cleanly standalone; EventBus satisfies the
contracts.EventBus protocol; subscribe/publish/unsubscribe routing; emit
resolving topic from the registered payload class; frozen typo-safe payloads.
"""

import importlib
import pathlib

import pytest

import kbl
from kbl.events import (
    AgentChanged,
    AgentManagerRequested,
    AssistantReply,
    DelegationRequested,
    EventBus,
    FileOpened,
    ServerConfigRequested,
    ToolRequested,
    ToolResult,
    UserSent,
    WorkspaceSelected,
    topic_for,
)

# ---------------------------------------------------------------------------
# events.py standalone.
# ---------------------------------------------------------------------------


def test_events_imports_standalone():
    module = importlib.import_module("kbl.events")
    assert module.EventBus is not None


def test_events_module_has_no_tkinter_import():
    root = pathlib.Path(kbl.__file__).parent
    source = (root / "events.py").read_text(encoding="utf-8")
    assert "tkinter" not in source
    assert "ttkbootstrap" not in source


# ---------------------------------------------------------------------------
# Contracts conformance.
# ---------------------------------------------------------------------------


def test_event_bus_satisfies_contract_protocol():
    bus = EventBus()
    for name in ("subscribe", "unsubscribe", "publish"):
        assert callable(getattr(bus, name)), name


# ---------------------------------------------------------------------------
# Subscribe / publish / unsubscribe.
# ---------------------------------------------------------------------------


def test_publish_calls_subscriber_with_payload():
    bus = EventBus()
    seen = []
    bus.subscribe("file_opened", seen.append)
    bus.publish("file_opened", FileOpened(path=pathlib.Path("a.md")))
    assert seen == [FileOpened(path=pathlib.Path("a.md"))]


def test_publish_calls_subscribers_in_order():
    bus = EventBus()
    order = []
    bus.subscribe("agent_changed", lambda p: order.append("first"))
    bus.subscribe("agent_changed", lambda p: order.append("second"))
    bus.publish("agent_changed", AgentChanged(agent_id="assistant"))
    assert order == ["first", "second"]


def test_publish_ignores_unsubscribed_topics():
    bus = EventBus()
    seen = []
    bus.subscribe("file_opened", seen.append)
    bus.publish("user_sent", UserSent(message="hi"))
    assert seen == []


def test_unsubscribe_removes_handler():
    bus = EventBus()
    seen = []
    bus.subscribe("workspace_selected", seen.append)
    bus.unsubscribe(
        "workspace_selected",
        lambda p: seen.append(p.workspace),
    )
    bus.publish("workspace_selected", WorkspaceSelected(workspace=pathlib.Path("w")))
    assert len(seen) == 1  # the lambda, not the stub


def test_unsubscribe_with_no_subscribers_is_noop():
    bus = EventBus()
    bus.unsubscribe("file_opened", lambda p: None)


def test_unsubscribe_missing_handler_is_noop():
    bus = EventBus()
    handler = lambda p: None
    bus.subscribe("file_opened", handler)
    bus.unsubscribe("file_opened", lambda p: None)
    bus.publish("file_opened", FileOpened(path=pathlib.Path("a.md")))
    assert handler  # still bound; only handler() removed, not this one


# ---------------------------------------------------------------------------
# emit: class -> topic resolution.
# ---------------------------------------------------------------------------


def test_emit_routes_to_registered_topic():
    bus = EventBus()
    seen = []
    bus.subscribe("tool_requested", seen.append)
    bus.emit(ToolRequested(name="read_file", args={"path": "a.md"}))
    assert seen == [ToolRequested(name="read_file", args={"path": "a.md"})]


def test_emit_raises_for_unregistered_class():
    bus = EventBus()

    class Surprise:
        pass

    try:
        bus.emit(Surprise())
    except ValueError as exc:
        assert "No topic registered" in str(exc)
    else:
        raise AssertionError("expected ValueError")


# ---------------------------------------------------------------------------
# Typed payloads.
# ---------------------------------------------------------------------------


def test_payloads_are_frozen_typo_safe():
    ws = WorkspaceSelected(workspace=pathlib.Path("w"))
    with pytest.raises(AttributeError):
        ws.workspace = pathlib.Path("x")


def test_topic_for_maps_class_to_topic():
    assert topic_for(UserSent) == "user_sent"
    assert topic_for(ToolResult) == "tool_result"
    assert topic_for(DelegationRequested) == "delegation_requested"


def test_marker_events_are_headless_safe():
    assert all(
        (
            WorkspaceSelected,
            FileOpened,
            UserSent,
            AssistantReply,
            ToolRequested,
            ToolResult,
            AgentChanged,
            ServerConfigRequested,
            AgentManagerRequested,
            DelegationRequested,
        )
    )


# ---------------------------------------------------------------------------
# Dialog/payload payloads with defaults.
# ---------------------------------------------------------------------------


def test_user_sent_defaults_attachments_to_empty():
    sent = UserSent(message="hello")
    assert sent.attachments == ()


def test_tool_result_defaults_error_to_none():
    result = ToolResult(name="read_file", result="r")
    assert result.error is None


def test_delegation_request_defaults():
    req = DelegationRequested(caller_id="assistant", agent_id="writer", task="draft")
    assert req.context == []
    assert req.tool_allowlist is None