"""M5: the delegation orchestrator.

Pure service — must never import Tkinter (guarded by tests/test_purity.py).

A sub-agent delegation is a scoped ``harness.orchestrate`` run:

- it owns a fresh conversation list seeded from the request's explicit
  ``context`` plus the delegated ``task`` (never any implicit history),
- its tool list is the child agent's own list (its ``allowed_tools`` filter,
  further intersected by the request's ``tool_allowlist``), so a parent's
  allowlist never grants the child a tool the child's own allowlist forbids,
- it shares the delegate-side turn budget: every sub-agent reserves its agent's
  ``max_turns`` against a config cap (``max_delegated_turns``), and the
  reserved depth is checked against the child's ``max_depth``,
- cancellation is passed through: the child loop receives the same
  ``stop_event`` as the parent, so aborting the root stops the whole tree.

Lifecycle is surfaced to a frontend via ``event_sink``: a callable
``(kind, value)`` that receives ``DelegationRequested``, ``SubagentStarted``,
``SubagentEvent``, ``SubagentCompleted``, and ``SubagentFailed`` payloads from
``kbl.events`` — all carrying the same ``task_id`` for correlation.

The delegator never talks to the LLM itself; it receives a ``run_agent``
callable (the harness's recursive orchestrator) at construction time. This
keeps the module acyclic: :mod:`kbl.harness` imports it, never the reverse.
"""

import json
import uuid

from kbl import agents
from kbl.contracts import DelegationRequest, DelegationResult
from kbl.events import (
    DELEGATION_REQUESTED,
    SUBAGENT_COMPLETED,
    SUBAGENT_EVENT,
    SUBAGENT_FAILED,
    SUBAGENT_STARTED,
    DelegationRequested,
    SubagentCompleted,
    SubagentEvent,
    SubagentFailed,
    SubagentStarted,
)
from kbl.tools import Tool

DEFAULT_MAX_DELEGATED_TURNS = 32
DELEGATE_TOOL_NAME = "delegate"

_UNKNOWN_ACTOR = "delegate: caller agent not found"
_NO_CHILD = "delegate: agent {0!r} not found"
_NOT_DELEGABLE = "delegate: agent {0!r} is not in '{1}'s can_delegate_to list"
_DEPTH_CAP = "delegate: max nesting depth {0} reached"
_BUDGET_CAP = "delegate: delegated turn budget exhausted"
_NO_RUNNER = "delegate: subagent runner unavailable"


def max_delegated_turns(config, default=DEFAULT_MAX_DELEGATED_TURNS):
    """Total sub-agent turn budget for one run, from user config.

    Falls back to ``default`` when the configured value is missing,
    non-integer, or below one.
    """
    if config is None:
        return default
    try:
        value = int(config.data.get("max_delegated_turns") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value >= 1 else default


def _delegate_parameters():
    return {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": "Agent to delegate to (must be in your "
                "can_delegate_to list).",
            },
            "task": {
                "type": "string",
                "description": "What the sub-agent should accomplish.",
            },
            "context": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Optional explicit context messages "
                "({'role': '...', 'content': '...'}). The sub-agent starts "
                "from these only, never from your history.",
            },
            "tool_allowlist": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional further restriction of the "
                "sub-agent's tool set.",
            },
        },
        "required": ["agent_id", "task"],
    }


def make_delegate_tool():
    """The ``delegate`` tool offered to agents that may delegate.

    The harness intercepts ``delegate`` calls before :func:`run_tool`; the
    placeholder ``func`` is only reached if the tool is executed outside a
    harness loop (e.g. by a user tool), in which case it explains itself.
    """
    return Tool(
        name=DELEGATE_TOOL_NAME,
        description=(
            "Delegate a sub-task to another agent in your can_delegate_to "
            "list. You only receive the delegated result, never the "
            "sub-agent's conversation."
        ),
        parameters=_delegate_parameters(),
        func=lambda **kwargs: (
            "<delegate> is handled by the harness delegation orchestrator."
        ),
    )


def invoke_delegate(delegator, call, caller_id, stop_event=None, depth=0):
    """Parse a ``delegate`` tool call and run it against ``delegator``.

    Returns the result string fed back to the parent model as the tool result.
    """
    try:
        args = json.loads(call.get("arguments") or "{}")
    except (TypeError, ValueError):
        return "delegate: could not parse arguments"
    if not isinstance(args, dict):
        return "delegate: arguments must be an object"
    agent_id = (args.get("agent_id") or "").strip()
    task = (args.get("task") or "").strip()
    if not agent_id or not task:
        return "delegate: agent_id and task are required"
    context = args.get("context")
    if not isinstance(context, list):
        context = []
    raw_allowlist = args.get("tool_allowlist")
    allowlist = (
        set(raw_allowlist) if isinstance(raw_allowlist, list) else None
    )
    request = DelegationRequest(
        caller_id=caller_id,
        agent_id=agent_id,
        task=task,
        context=context,
        tool_allowlist=allowlist,
    )
    return delegator.delegate(request, stop_event=stop_event, depth=depth).result


class SubagentDelegator:
    """M5 standing implementation of ``contracts.Delegator``.

    Isolated scope per delegation: fresh conversation, scoped tool list,
    depth/turn caps, and a shared ``event_sink`` for lifecycle correlation.
    """

    def __init__(
        self,
        config,
        workspace=None,
        event_sink=None,
        run_agent=None,
    ):
        self.config = config
        self.workspace = workspace
        self.event_sink = event_sink
        self._run_agent = run_agent
        self._budget = max_delegated_turns(config)
        self._used_turns = 0

    # ---- event sink ----

    def _sink(self, kind, payload):
        if self.event_sink is not None:
            self.event_sink(kind, payload)

    # ---- delegation ----

    def delegate(self, request, stop_event=None, depth=0):
        child_id = request.agent_id
        caller_id = request.caller_id
        try:
            caller = agents.load_agent(caller_id) if caller_id else None
        except agents.AgentError:
            caller = None
        if caller is None:
            return self._fail(request, _UNKNOWN_ACTOR)
        try:
            child = agents.load_agent(child_id)
        except agents.AgentError:
            return self._fail(request, _NO_CHILD.format(child_id))
        if child_id not in set(caller.can_delegate_to or []):
            return self._fail(request, _NOT_DELEGABLE.format(child_id, caller_id))
        if depth >= int(child.max_depth):
            return self._fail(request, _DEPTH_CAP.format(child.max_depth))
        cost = int(child.max_turns)
        if self._used_turns + cost > self._budget:
            return self._fail(request, _BUDGET_CAP)
        self._used_turns += cost

        task_id = uuid.uuid4().hex[:12]
        self._sink(
            DELEGATION_REQUESTED,
            DelegationRequested(
                caller_id=caller_id,
                agent_id=child_id,
                task=request.task,
                context=list(request.context),
                tool_allowlist=request.tool_allowlist,
            ),
        )
        self._sink(SUBAGENT_STARTED, SubagentStarted(task_id=task_id, agent_id=child_id))
        if self._run_agent is None:
            self._sink(SUBAGENT_FAILED, SubagentFailed(task_id=task_id, error=_NO_RUNNER))
            return DelegationResult(task_id=task_id, result=_NO_RUNNER)

        conversation = list(request.context or [])
        conversation.append({"role": "user", "content": request.task})
        text_parts = []
        tool_calls = []
        try:
            for event in self._run_agent(
                self.config,
                self.workspace,
                conversation,
                stop_event,
                agent_id=child_id,
                depth=depth + 1,
                max_rounds=cost,
                allowlist=request.tool_allowlist,
            ):
                if event.kind != "done":
                    self._sink(SUBAGENT_EVENT, SubagentEvent(task_id=task_id, event=event))
                if event.kind == "content":
                    text_parts.append(event[1])
                elif event.kind == "tool_call":
                    tool_calls.append(dict(event[1]))
                elif event.kind == "error":
                    message = event[1]
                    self._sink(SUBAGENT_FAILED, SubagentFailed(task_id=task_id, error=message))
                    return DelegationResult(task_id=task_id, result=message)
            result_text = "".join(text_parts)
            self._sink(
                SUBAGENT_COMPLETED,
                SubagentCompleted(
                    task_id=task_id,
                    result=result_text,
                    tool_calls=tool_calls or None,
                ),
            )
            return DelegationResult(
                task_id=task_id,
                result=result_text,
                tool_calls=tool_calls or None,
            )
        except Exception as exc:
            message = f"delegate failed: {exc}"
            self._sink(SUBAGENT_FAILED, SubagentFailed(task_id=task_id, error=message))
            return DelegationResult(task_id=task_id, result=message)

    def _fail(self, request, message):
        task_id = uuid.uuid4().hex[:12]
        self._sink(SUBAGENT_FAILED, SubagentFailed(task_id=task_id, error=message))
        return DelegationResult(task_id=task_id, result=message)