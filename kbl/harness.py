"""Agent-loop orchestration harness.

Pure service — must never import Tkinter (guarded by tests/test_purity.py).
Extracted from the chat panel so the LLM/tool loop can be run headlessly,
tested, and reused by any frontend.

``orchestrate()`` is a generator over the full agent loop: it streams the
model's reply through ``chat_stream``, and when the model asks for tool calls
it executes them via :func:`kbl.tools.run_tool` and feeds the results back for
another round, capped by the configured ``max_tool_rounds``.

Events yielded are the :class:`~kbl.contracts.StreamEvent` union — typed
NamedTuples whose first element is the event kind, so a panel can pump them
into a queue and unpack ``kind, value = event``::

    Content("content", text)                -- assistant answer token stream
    Reasoning("reasoning", text)            -- thinking token stream
    ToolCall("tool_call", {"id","name","arguments"})
    ToolResult("tool_result", (call, result))  -- result is always a string
    Done("done", final_text)                -- loop finished normally
    Error("error", message)                 -- fatal, or rounds exhausted

The harness owns conversation state: on completion it appends the tool message
round-trips and the final assistant reply to the passed ``conversation`` list
(unless stopped). It never touches widgets; the frontend is responsible for
running it on a worker thread and marshalling events back to the UI.
"""

from typing import Iterator

from kbl import agents, context, toolstore
from kbl.chat_client import chat_stream
from kbl.contracts import Harness, StreamEvent, make_stream_event
from kbl.delegator import (
    DELEGATE_TOOL_NAME,
    SubagentDelegator,
    invoke_delegate,
    make_delegate_tool,
)
from kbl.tools import run_tool

DEFAULT_MAX_TOOL_ROUNDS = 8


def max_tool_rounds(config, default=DEFAULT_MAX_TOOL_ROUNDS):
    """Tool-call round cap for an agent loop, from user config.

    Falls back to ``default`` when the configured value is missing, non-integer,
    or below one (a single round is the minimum that makes sense).
    """
    if config is None:
        return default
    try:
        value = int(config.data.get("max_tool_rounds") or 0)
    except (TypeError, ValueError):
        value = 0
    return value if value >= 1 else default


def build_request(config, workspace=None, agent_id=None):
    """Resolve the environment for one send: tool list + composed system prompt.

    ``agent_id`` selects the agent whose allowlist and delegation settings are
    applied (default: the configured active agent). When the agent may
    delegate, a ``delegate`` tool is appended after allowlist filtering so the
    model can dispatch sub-tasks.
    """
    collection = toolstore.collect_tools(workspace, config)
    tool_list = list(collection.enabled_tools)
    active = agent_id or agents.active_agent(config)
    agent = agents.load_agent(active)
    if agent.allowed_tools is not None:
        allowed = set(agent.allowed_tools)
        tool_list = [t for t in tool_list if t.name in allowed]
    if agent.can_delegate_to:
        tool_list = list(tool_list) + [make_delegate_tool()]
    system_prompt = context.compose_system(
        agents.get_prompt(active),
        context.workspace_instructions(workspace),
        tool_list,
        skills=collection.skills,
    )
    return system_prompt, tool_list


def _normalize_call(call, seq):
    return {
        "id": call.get("id") or f"call_{seq}",
        "name": call.get("name") or "",
        "arguments": call.get("arguments") or "{}",
    }


def _assistant_tool_message(calls):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": call["arguments"],
                },
            }
            for call in calls
        ],
    }


def orchestrate(
    server,
    model,
    api_key,
    conversation,
    workspace=None,
    config=None,
    stop_event=None,
    tools=None,
    system_prompt=None,
    max_rounds=None,
    *,
    agent_id=None,
    depth=0,
    delegator=None,
    event_sink=None,
) -> Iterator[StreamEvent]:
    """Run the agent loop, yielding events as it goes.

    This is the M2 :class:`~kbl.contracts.Harness` implementation: a
    synchronous generator of :class:`~kbl.contracts.StreamEvent`s.

    ``conversation`` is the mutable history list; tool results and the final
    assistant reply are appended to it when the loop does not end via stop.

    ``tools`` and ``system_prompt`` may be supplied directly for testability;
    otherwise they are built from ``config`` (and ``workspace``) via
    :func:`build_request`.

    M5 (keyword-only): ``agent_id`` pins which agent this loop runs as (used
    for recursion and for the delegate tool's caller); ``depth`` is the
    delegation nesting level; ``delegator`` injects a delegation engine; and
    ``event_sink`` receives ``(kind, value)`` lifecycle payloads for
    sub-agents started through the ``delegate`` tool.
    """
    if tools is None or system_prompt is None:
        if config is None:
            raise ValueError(
                "config is required when tools/system_prompt are not supplied"
            )
        built_system_prompt, built_tools = build_request(config, workspace, agent_id=agent_id)
        if system_prompt is None:
            system_prompt = built_system_prompt
        if tools is None:
            tools = built_tools
    rounds = max_rounds if max_rounds is not None else max_tool_rounds(config)

    caller_id = agent_id or (agents.active_agent(config) if config is not None else None)

    delegator_holder = [delegator]

    def _run_agent(
        config,
        workspace,
        conversation,
        stop_event,
        *,
        agent_id,
        depth,
        max_rounds,
        allowlist,
    ):
        child_prompt, child_tools = build_request(config, workspace, agent_id=agent_id)
        if allowlist is not None:
            allowed = set(allowlist)
            child_tools = [t for t in child_tools if t.name in allowed]
        return orchestrate(
            server,
            model,
            api_key,
            conversation,
            workspace=workspace,
            config=config,
            stop_event=stop_event,
            tools=child_tools,
            system_prompt=child_prompt,
            max_rounds=max_rounds,
            agent_id=agent_id,
            depth=depth,
            delegator=delegator_holder[0],
            event_sink=event_sink,
        )

    def _get_delegator():
        if delegator_holder[0] is None:
            delegator_holder[0] = SubagentDelegator(
                config,
                workspace=workspace,
                event_sink=event_sink,
                run_agent=_run_agent,
            )
        return delegator_holder[0]

    tool_messages = []
    content_parts = []
    call_seq = 0
    try:
        for _round in range(rounds):
            base = [{"role": "system", "content": system_prompt}] + list(conversation)
            calls = None
            for kind, piece in chat_stream(
                server,
                model,
                base + tool_messages,
                api_key,
                stop_event,
                tools=tools or [],
            ):
                if kind == "tool_calls":
                    calls = piece
                    continue
                if kind == "content":
                    content_parts.append(piece)
                yield make_stream_event(kind, piece)
            if calls is None:
                break
            if stop_event is not None and stop_event.is_set():
                break
            normalized = []
            for i, call in enumerate(calls, call_seq):
                normalized.append(_normalize_call(call, i))
            call_seq += len(normalized)
            tool_messages.append(_assistant_tool_message(normalized))
            for call in normalized:
                if call["name"] == DELEGATE_TOOL_NAME:
                    result = invoke_delegate(
                        _get_delegator(), call, caller_id, stop_event, depth
                    )
                else:
                    result = run_tool(tools or [], call["name"], call["arguments"])
                yield make_stream_event("tool_call", call)
                yield make_stream_event("tool_result", (call, result))
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": result,
                    }
                )
        else:
            yield make_stream_event("error", f"Stopped after {rounds} tool rounds.")
            return
        final_text = "".join(content_parts)
        if stop_event is None or not stop_event.is_set():
            conversation.extend(tool_messages)
            if final_text:
                conversation.append({"role": "assistant", "content": final_text})
        yield make_stream_event("done", final_text)
    except Exception as exc:
        yield make_stream_event("error", str(exc))