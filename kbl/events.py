"""Event bus (M3): typed publish/subscribe wiring between components.

Replaces the ``self.master`` reach-in plumbing and cross-panel constructor
callbacks with typed events. The bus is UI-thread only: worker threads hand
events to the UI thread through their queues, and the UI thread publishes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

Handler = Callable[[Any], None]

WORKSPACE_SELECTED = "workspace_selected"
FILE_OPENED = "file_opened"
USER_SENT = "user_sent"
ASSISTANT_REPLY = "assistant_reply"
TOOL_REQUESTED = "tool_requested"
TOOL_RESULT = "tool_result"
AGENT_CHANGED = "agent_changed"
SERVER_CONFIG_REQUESTED = "server_config_requested"
AGENT_MANAGER_REQUESTED = "agent_manager_requested"
TOOL_MANAGER_REQUESTED = "tool_manager_requested"
DELEGATION_REQUESTED = "delegation_requested"
SUBAGENT_STARTED = "subagent_started"
SUBAGENT_EVENT = "subagent_event"
SUBAGENT_COMPLETED = "subagent_completed"
SUBAGENT_FAILED = "subagent_failed"


@dataclass(frozen=True)
class WorkspaceSelected:
    workspace: Path


@dataclass(frozen=True)
class FileOpened:
    path: Path


@dataclass(frozen=True)
class UserSent:
    message: str
    attachments: tuple[Path, ...] = ()


@dataclass(frozen=True)
class AssistantReply:
    message: str


@dataclass(frozen=True)
class ToolRequested:
    name: str
    args: dict


@dataclass(frozen=True)
class ToolResult:
    name: str
    result: str
    error: str | None = None


@dataclass(frozen=True)
class AgentChanged:
    agent_id: str


@dataclass(frozen=True)
class ServerConfigRequested:
    pass


@dataclass(frozen=True)
class AgentManagerRequested:
    pass


@dataclass(frozen=True)
class ToolManagerRequested:
    pass


@dataclass(frozen=True)
class DelegationRequested:
    caller_id: str
    agent_id: str
    task: str
    context: list[dict] = field(default_factory=list)
    tool_allowlist: set[str] | None = None


@dataclass(frozen=True)
class SubagentStarted:
    task_id: str
    agent_id: str


@dataclass(frozen=True)
class SubagentEvent:
    task_id: str
    event: Any


@dataclass(frozen=True)
class SubagentCompleted:
    task_id: str
    result: str
    tool_calls: list | None = None


@dataclass(frozen=True)
class SubagentFailed:
    task_id: str
    error: str


_TOPIC_BY_CLASS: dict[type, str] = {}


def _register(cls: type, topic: str) -> type:
    _TOPIC_BY_CLASS[cls] = topic
    return cls


_TOPIC_BY_CLASS.update(
    {
        WorkspaceSelected: WORKSPACE_SELECTED,
        FileOpened: FILE_OPENED,
        UserSent: USER_SENT,
        AssistantReply: ASSISTANT_REPLY,
        ToolRequested: TOOL_REQUESTED,
        ToolResult: TOOL_RESULT,
        AgentChanged: AGENT_CHANGED,
        ServerConfigRequested: SERVER_CONFIG_REQUESTED,
        AgentManagerRequested: AGENT_MANAGER_REQUESTED,
        ToolManagerRequested: TOOL_MANAGER_REQUESTED,
        DelegationRequested: DELEGATION_REQUESTED,
        SubagentStarted: SUBAGENT_STARTED,
        SubagentEvent: SUBAGENT_EVENT,
        SubagentCompleted: SUBAGENT_COMPLETED,
        SubagentFailed: SUBAGENT_FAILED,
    }
)


class EventBus:
    """Synchronous, in-process publish/subscribe bus.

    Satisfies :class:`kbl.contracts.EventBus`. Handlers run inline, in
    subscription order, on the thread that publishes (the UI thread).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}

    def subscribe(self, topic: str, handler: Handler) -> None:
        self._subscribers.setdefault(topic, []).append(handler)

    def unsubscribe(self, topic: str, handler: Handler) -> None:
        handlers = self._subscribers.get(topic)
        if not handlers:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            pass

    def publish(self, topic: str, payload: Any = None) -> None:
        for handler in list(self._subscribers.get(topic, ())):
            handler(payload)

    def emit(self, event: Any) -> None:
        """Publish ``event`` using the topic registered for its class."""
        topic = _TOPIC_BY_CLASS.get(type(event))
        if topic is None:
            raise ValueError(f"No topic registered for {type(event).__name__}")
        self.publish(topic, event)


def topic_for(event_type: type) -> str:
    return _TOPIC_BY_CLASS[event_type]