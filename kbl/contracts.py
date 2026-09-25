"""Contract surface for the KBL framework (architecture doc, section 5).

Pure module — must never import Tkinter (guarded by tests/test_purity.py).

Every contract here is **synchronous**: the app's concurrency model is plain
calls, ``threading.Event`` for cancellation, and ``root.after``-marshalled
events back to the UI thread. There is intentionally no asyncio anywhere
(the architecture doc's original ``async`` Harness sketch was dropped during
planning — see the roadmap).

Two kinds of declarations live here:

- **Typed value types** that already exist at runtime (``StreamEvent`` and its
  variants, ``DelegationRequest``/``DelegationResult``).
- **Contracts** (:class:`Protocol`) describing what a component *is*. Several
  are implemented today (``WorkspaceProvider`` → ``kbl.workspaces``,
  ``ConfigStore`` → ``kbl.config``, ``Harness`` → ``kbl.harness.orchestrate``,
  ``DisplayRenderer`` → ``kbl.markdown_render.MarkdownRenderer``); the rest
  are forward declarations for later milestones, so downstream M5/M6 work has
  a fixed target to implement against.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Literal, NamedTuple, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# StreamEvent: the typed event union a Harness stream yields.
# ---------------------------------------------------------------------------


class Content(NamedTuple):
    kind: Literal["content"] = "content"
    text: str = ""


class Reasoning(NamedTuple):
    kind: Literal["reasoning"] = "reasoning"
    text: str = ""


class ToolCall(NamedTuple):
    kind: Literal["tool_call"] = "tool_call"
    call: dict = ()


class ToolResult(NamedTuple):
    kind: Literal["tool_result"] = "tool_result"
    # (call: dict, result: str)
    payload: tuple = ()


class Done(NamedTuple):
    kind: Literal["done"] = "done"
    text: str = ""


class Error(NamedTuple):
    kind: Literal["error"] = "error"
    message: str = ""


StreamEvent = Content | Reasoning | ToolCall | ToolResult | Done | Error

_STREAM_KINDS = {
    "content": Content,
    "reasoning": Reasoning,
    "tool_call": ToolCall,
    "tool_result": ToolResult,
    "done": Done,
    "error": Error,
}


def make_stream_event(kind: str, payload) -> StreamEvent:
    """Build the right StreamEvent variant for a ``(kind, payload)`` pair.

    Each variant is a NamedTuple whose first element is the ``kind`` string, so
    a StreamEvent compares equal to the ``(kind, payload)`` tuple it replaces
    and keeps working anywhere queue-drain code unpacks ``kind, value = ev``.
    """
    variant = _STREAM_KINDS.get(kind)
    if variant is None:
        raise ValueError(f"Unknown stream event kind: {kind!r}")
    return variant(kind, payload)


# ---------------------------------------------------------------------------
# Contracts.
# ---------------------------------------------------------------------------


@runtime_checkable
class Harness(Protocol):
    """The LLM/tool loop. Implemented today by ``kbl.harness.orchestrate``.

    This types the *real* entry point (the architecture doc sketched an async
    ``send(messages, tools, workspace, stop_event, ...)``; the synchronous
    generator retained is ``orchestrate``). It is a :class:`Protocol` with a
    ``__call__`` member so the plain function version passes structural
    isinstance checks, and a future object-based harness (e.g. an SD-branch
    backend in M6) satisfies it equally.
    """

    def __call__(
        self,
        server: str,
        model: str,
        api_key: str,
        conversation: list[dict],
        workspace: Path | None = None,
        config: ConfigStore | None = None,
        stop_event: threading.Event | None = None,
        tools: list | None = None,
        system_prompt: str | None = None,
        max_rounds: int | None = None,
        *,
        agent_id: str | None = None,
        depth: int = 0,
        delegator: Delegator | None = None,
        event_sink: Callable[[str, object], None] | None = None,
    ) -> Iterator[StreamEvent]: ...


@runtime_checkable
class DisplayRenderer(Protocol):
    """Renders a markdown string into a widget surface."""

    def setup(self, device) -> None: ...
    def render(self, device, md_text: str) -> None: ...
    def append(self, device, md_text: str, index: str = "end") -> None: ...


@runtime_checkable
class Device(Protocol):
    """The bare widget surface a :class:`DisplayRenderer` writes into.

    The concrete implementation is a ``tkinter.Text`` widget; only the
    operations markdown rendering touches are declared.
    """

    def cget(self, option: str): ...
    def tag_configure(self, tagname: str, **kw) -> None: ...
    def configure(self, cnf=None, **kw) -> None: ...
    def delete(self, index1, index2=None) -> None: ...
    def insert(self, index, chars, *args) -> None: ...


@runtime_checkable
class WorkspaceProvider(Protocol):
    """The set of registered workspaces plus the session-active one.

    Implemented today by ``kbl.workspaces.WorkspaceManager``.
    """

    @property
    def workspaces(self) -> list[Path]: ...
    @property
    def active(self) -> Path | None: ...
    def register(self, path) -> Path: ...
    def add(self, path) -> Path: ...
    def remove(self, path) -> None: ...
    def set_active(self, path, persist_default: bool = False) -> None: ...


@runtime_checkable
class ConfigStore(Protocol):
    """Persisted application configuration.

    Implemented today by ``kbl.config.Config``. Note: ``Config()`` (no path)
    is a deliberate process-wide singleton — tools call ``Config()`` from the
    worker thread and must observe the same in-memory state as the app,
    including the per-instance ``active_workspace``, which is never persisted.
    """

    path: Path
    data: dict

    def load(self) -> dict: ...
    def save(self, merge: bool = True) -> None: ...


@runtime_checkable
class ToolCollection(Protocol):
    """The resolved tool set for one workspace (see ``kbl.toolstore``)."""

    enabled_tools: list
    skills: list
    all_skills: list
    warnings: list


class ToolRegistry(Protocol):
    """Discovers and disables tools (built-ins, global, per-workspace).

    Forward contract — stood up as a registry object in M4; today the
    functions of ``kbl.toolstore`` (``collect_tools``, ``set_disabled``)
    provide the standing implementation.
    """

    def collect_tools(self, workspace, config) -> ToolCollection: ...
    def set_disabled(self, config, name: str, disabled: bool) -> None: ...


class FileRepository(Protocol):
    """The wiki's file surface the built-in tools expose to the model.

    Forward contract describing the standing set of file operations in
    ``kbl.tools`` (list/read/search/headings/create/edit), bound to a
    workspace by ``kbl.tools.builtin_tools``.
    """

    def list_md_files(self, workspace) -> list[str]: ...
    def read_file(self, workspace, path: str) -> str: ...
    def search_files(self, workspace, query: str) -> str: ...
    def get_headings(self, workspace, path: str) -> str: ...
    def create_file(self, workspace, path: str, content: str = "") -> str: ...
    def edit_file(self, workspace, path: str, new_content: str) -> str: ...


class EventBus(Protocol):
    """Mediates publish/subscribe between app components.

    Forward contract (M3): replaces the ``self.master`` reach-in wiring with
    typed events (WorkspaceSelected, FileOpened, UserSent, AssistantReply,
    ToolRequested, ToolResult, AgentChanged, Delegation events, ...).
    """

    def subscribe(self, topic: str, handler) -> None: ...
    def unsubscribe(self, topic: str, handler) -> None: ...
    def publish(self, topic: str, payload=None) -> None: ...


class Agent(Protocol):
    """The configuration + personality of one assistant identity.

    Forward contract (M4). Backward compatible with the current layout
    ``~/.kbl/agents/<name>/system_prompt.md``.
    """

    id: str
    prompt_path: Path
    description: str | None
    role: str | None
    allowed_tools: list[str] | None  # None = every enabled tool
    parent: str | None
    can_delegate_to: list[str]
    max_turns: int
    max_depth: int


class AgentRegistry(Protocol):
    """Looks up agents and which agents may delegate to which.

    Forward contract (M4), standing implementation in ``kbl.agents``.
    """

    def list_agents(self) -> list[Agent]: ...
    def get(self, agent_id: str) -> Agent: ...
    def active(self, config: ConfigStore) -> str: ...
    def can_delegate_to(self, agent_id: str) -> list[str]: ...


@dataclass(frozen=True)
class DelegationRequest:
    """One subagent invocation (forward contract, M5)."""

    caller_id: str
    agent_id: str
    task: str
    context: list[dict] = field(default_factory=list)
    tool_allowlist: set[str] | None = None


@dataclass(frozen=True)
class DelegationResult:
    """The terminal summary of one subagent run (forward contract, M5)."""

    task_id: str
    result: str
    tool_calls: list | None = None


class SubagentRegistry(Protocol):
    """Tracks in-flight delegated subagents by ``task_id`` (forward, M5)."""

    def start(self, request: DelegationRequest, stop_event: threading.Event) -> str: ...
    def iter_events(self, task_id: str) -> Iterator[StreamEvent]: ...
    def cancel(self, task_id: str) -> None: ...


class Delegator(Protocol):
    """Executes a delegated task in an isolated scope (forward, M5).

    Isolation mandate: its own conversation/thread, an explicit context (never
    implicit full history), a scoped tool allowlist, and cancellation that
    propagates down the tree.
    """

    def delegate(
        self, request: DelegationRequest, stop_event: threading.Event | None = None
    ) -> DelegationResult: ...