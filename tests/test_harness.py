"""Tests for kbl.harness: the LLM/tool agent loop.

No network access: a fake ``chat_stream`` is injected via monkeypatch on
``harness.chat_stream``, and a stub ``harness.run_tool`` stands in for tool
execution. ``schedule[tool_count]`` chooses the fake stream's events for a
round based on how many tool messages are already queued.
"""

import threading

from kbl import agents, harness
from kbl.tools import Tool

_ADD = {
    "id": "call_1",
    "name": "add",
    "arguments": '{"a": 1, "b": 2}',
}


def _fake_chat_stream(schedules, log=None):
    def fake(server, model, messages, api_key, stop_event=None, tools=None):
        if stop_event is not None and stop_event.is_set():
            return
        if log is not None:
            log.append(messages)
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        entry = schedules[min(tool_count, len(schedules) - 1)]
        yield from entry if isinstance(entry, (list, tuple)) else entry(messages)

    return fake


def test_single_round_no_tools(monkeypatch):
    monkeypatch.setattr(
        harness, "chat_stream",
        _fake_chat_stream([[("content", "hi "), ("content", "there")]]),
    )
    conversation = [{"role": "user", "content": "hello"}]
    events = list(
        harness.orchestrate(
            "http://x", "model", "", conversation,
            system_prompt="You are a test assistant.",
            tools=[], max_rounds=8,
        )
    )
    assert events == [("content", "hi "), ("content", "there"), ("done", "hi there")]
    assert conversation == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_tool_round_trip(monkeypatch):
    log = []
    monkeypatch.setattr(
        harness, "chat_stream",
        _fake_chat_stream(
            [[("tool_calls", [_ADD])], [("content", "= 3")]], log=log,
        ),
    )
    monkeypatch.setattr(harness, "run_tool", lambda tools, name, args: "3")
    events = []
    orchestrated = harness.orchestrate(
        "http://x", "model", "", [],
        system_prompt="You are a test assistant.",
        tools=[Tool("add", "adds numbers", {"type": "object", "properties": {}}, lambda: "3")],
        max_rounds=8,
    )
    for ev in orchestrated:
        events.append(ev)
    call = {"id": "call_1", "name": "add", "arguments": '{"a": 1, "b": 2}'}
    assert events == [
        ("tool_call", call),
        ("tool_result", (call, "3")),
        ("content", "= 3"),
        ("done", "= 3"),
    ]
    tool_messages = [m for m in log[1] if m.get("role") == "tool"]
    assert tool_messages == [{"role": "tool", "tool_call_id": "call_1", "content": "3"}]
    assistant_parts = [m for m in log[1] if m.get("role") == "assistant"]
    assert assistant_parts[0]["tool_calls"][0]["function"]["name"] == "add"


def test_loop_ends_when_no_tool_calls(monkeypatch):
    monkeypatch.setattr(
        harness, "chat_stream",
        _fake_chat_stream([[("content", "answer")]]),
    )
    conversation = [{"role": "user", "content": "q"}]
    events = list(
        harness.orchestrate(
            "http://x", "model", "", conversation,
            system_prompt="p", tools=[], max_rounds=8,
        )
    )
    assert events[-1] == ("done", "answer")
    assert [m["role"] for m in conversation] == ["user", "assistant"]


def test_max_rounds_cap(monkeypatch):
    always_tools = [[("tool_calls", [_ADD]), ("content", "")]]
    monkeypatch.setattr(harness, "chat_stream", _fake_chat_stream(always_tools))
    monkeypatch.setattr(harness, "run_tool", lambda tools, name, args: "3")
    conversation = [{"role": "user", "content": "q"}]
    events = list(
        harness.orchestrate(
            "http://x", "model", "", conversation,
            system_prompt="p", tools=[Tool("add", "n", {}, lambda: "3")],
            max_rounds=2,
        )
    )
    kinds = [k for k, _ in events]
    assert kinds[-1] == "error"
    assert "done" not in kinds
    assert events[-1] == ("error", "Stopped after 2 tool rounds.")
    assert conversation == [{"role": "user", "content": "q"}]


def test_stop_event_aborts(monkeypatch):
    stop = threading.Event()
    monkeypatch.setattr(harness, "chat_stream", _fake_chat_stream([[("content", "x")]]))
    conversation = [{"role": "user", "content": "q"}]
    stop.set()
    events = list(
        harness.orchestrate(
            "http://x", "model", "", conversation,
            stop_event=stop, system_prompt="p", tools=[], max_rounds=8,
        )
    )
    assert events == [("done", "")]
    assert conversation == [{"role": "user", "content": "q"}]


def test_stream_error_propagates_as_error_event(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(harness, "chat_stream", boom)
    events = list(
        harness.orchestrate(
            "http://x", "model", "", [],
            system_prompt="p", tools=[], max_rounds=8,
        )
    )
    assert events == [("error", "network down")]


def test_build_request_from_config(monkeypatch, tmp_config, workspace, kbl_dirs):
    system_prompt, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    assert "list_files" in names and "read_file" in names and "search_files" in names
    assert "## Workspace" in system_prompt
    assert "## Tools" in system_prompt
    assert "- list_files:" in system_prompt


def test_build_request_applies_agent_allowlist(tmp_config, workspace, kbl_dirs):
    agents.create_agent("restricted")
    agent = agents.load_agent("restricted")
    agent.allowed_tools = ["read_file"]
    agents.save_metadata("restricted", agent)
    tmp_config.data["active_agent"] = "restricted"

    system_prompt, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    tools_section = system_prompt.split("## Tools", 1)[1]
    assert "read_file" in names
    assert "list_files" not in names and "search_files" not in names
    assert "- read_file(" in tools_section
    assert "list_files" not in tools_section


def test_build_request_default_agent_gets_all_tools(tmp_config, workspace, kbl_dirs):
    system_prompt, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    assert "list_files" in names and "read_file" in names


def test_orchestrate_uses_config_when_parts_missing(monkeypatch, tmp_config, workspace, kbl_dirs):
    log = []
    monkeypatch.setattr(harness, "chat_stream", _fake_chat_stream([[("content", "ok")]], log=log))
    events = list(
        harness.orchestrate(
            "http://x", "model", "", [],
            workspace=str(workspace), config=tmp_config,
        )
    )
    assert events[-1] == ("done", "ok")
    first_messages = log[0]
    assert first_messages[0]["role"] == "system"
    assert "## Tools" in first_messages[0]["content"]


def test_orchestrate_requires_config_without_tools():
    try:
        list(harness.orchestrate("http://x", "model", "", []))
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "config is required" in str(exc)


def test_max_tool_rounds_reads_config():
    assert harness.max_tool_rounds(None) == harness.DEFAULT_MAX_TOOL_ROUNDS

    class C:
        data = {"max_tool_rounds": 12}

    assert harness.max_tool_rounds(C()) == 12

    class Bad:
        data = {"max_tool_rounds": "abc"}

    assert harness.max_tool_rounds(Bad()) == harness.DEFAULT_MAX_TOOL_ROUNDS

    class Low:
        data = {"max_tool_rounds": 0}

    assert harness.max_tool_rounds(Low()) == harness.DEFAULT_MAX_TOOL_ROUNDS


# ---------------------------------------------------------------------------
# M5: delegation through the harness.
# ---------------------------------------------------------------------------


def test_build_request_adds_delegate_tool_for_delegating_agent(tmp_config, workspace, kbl_dirs):
    agents.create_agent("delegator_agent")
    agent = agents.load_agent("delegator_agent")
    agent.can_delegate_to = ["writer"]
    agents.save_metadata("delegator_agent", agent)
    tmp_config.data["active_agent"] = "delegator_agent"

    system_prompt, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    assert "delegate" in names
    assert "- delegate(" in system_prompt


def test_build_request_omits_delegate_tool_by_default(tmp_config, workspace, kbl_dirs):
    system_prompt, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    assert "delegate" not in names


def test_build_request_allowlist_and_delegate_tool_coexist(tmp_config, workspace, kbl_dirs):
    agents.create_agent("delegator_agent")
    agent = agents.load_agent("delegator_agent")
    agent.can_delegate_to = ["writer"]
    agent.allowed_tools = ["read_file"]  # child's own tools unaffected
    agents.save_metadata("delegator_agent", agent)
    tmp_config.data["active_agent"] = "delegator_agent"

    _, tool_list = harness.build_request(tmp_config, str(workspace))
    names = [t.name for t in tool_list]
    assert "read_file" in names
    assert "delegate" in names
    assert "list_files" not in names


def test_orchestrate_delegates_tool_call(monkeypatch, tmp_config, workspace, kbl_dirs):
    """One parent agent delegates a sub-task to one child: end-to-end in harness."""
    from kbl.delegator import SubagentDelegator
    from kbl.events import (
        SUBAGENT_COMPLETED,
        SUBAGENT_STARTED,
        SubagentStarted,
        SubagentCompleted,
    )

    agents.create_agent("manager")
    manager = agents.load_agent("manager")
    manager.can_delegate_to = ["writer"]
    agents.save_metadata("manager", manager)
    agents.create_agent("writer")
    tmp_config.data["active_agent"] = "manager"

    delegate_call = {
        "id": "call_1",
        "name": "delegate",
        "arguments": '{"agent_id": "writer", "task": "summarize docs"}',
    }

    def schedule(messages):
        system = messages[0]["content"] if messages else ""
        tool_count = sum(1 for m in messages if m.get("role") == "tool")
        if tool_count == 0 and "- delegate(" in system:
            return [("tool_calls", [delegate_call])]
        return [("content", "done "), ("content", "here")]

    sink_events = []

    def event_sink(kind, value):
        sink_events.append((kind, value))

    monkeypatch.setattr(harness, "chat_stream", _fake_chat_stream([schedule]))
    monkeypatch.setattr(harness, "run_tool", lambda tools, name, args: f"<ran {name}>")

    conversation = [{"role": "user", "content": "q"}]
    events = list(
        harness.orchestrate(
            "http://x", "model", "", conversation,
            workspace=str(workspace), config=tmp_config, event_sink=event_sink,
        )
    )
    kinds = [k for k, _ in events]
    assert "tool_call" in kinds
    delegate_results = [
        result
        for kind, value in events
        if kind == "tool_result"
        for call, result in (value,)
        if call == delegate_call
    ]
    assert delegate_results, "delegate tool result missing"
    non_delegate_tools = [
        result
        for kind, value in events
        if kind == "tool_result"
        for call, result in (value,)
        if call != delegate_call
    ]
    assert not non_delegate_tools  # no non-delegate tool executed

    # Parent conversation only carries its own state (its own delegate round).
    assert conversation == [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "delegate", "arguments": delegate_call["arguments"]},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "done here"},
        {"role": "assistant", "content": "done here"},
    ]

    started = [v for k, v in sink_events if k == SUBAGENT_STARTED]
    completed = [v for k, v in sink_events if k == SUBAGENT_COMPLETED]
    assert len(started) == 1 and len(completed) == 1
    assert isinstance(started[0], SubagentStarted)
    assert isinstance(completed[0], SubagentCompleted)
    assert started[0].task_id == completed[0].task_id
    assert started[0].agent_id == "writer"
    assert completed[0].result == "done here"


def test_orchestrate_requires_real_delegator_for_depth(monkeypatch, tmp_config, workspace, kbl_dirs):
    """Injecting a stub delegator is honored; the default engine is created lazily."""
    from kbl.contracts import DelegationResult

    class Stub:
        def __init__(self):
            self.calls = []

        def delegate(self, request, stop_event=None, depth=0):
            self.calls.append(request)
            return DelegationResult(task_id="t_123", result="stubbed")

    agents.create_agent("manager")
    manager = agents.load_agent("manager")
    manager.can_delegate_to = ["writer"]
    agents.save_metadata("manager", manager)
    agents.create_agent("writer")
    tmp_config.data["active_agent"] = "manager"

    call = {
        "id": "call_1",
        "name": "delegate",
        "arguments": '{"agent_id": "writer", "task": "do it"}',
    }

    def schedule(messages):
        return [("tool_calls", [call])]

    stub = Stub()
    monkeypatch.setattr(harness, "chat_stream", _fake_chat_stream([schedule]))
    monkeypatch.setattr(harness, "run_tool", lambda tools, name, args: "unused")

    events = list(
        harness.orchestrate(
            "http://x", "model", "", [],
            workspace=str(workspace), config=tmp_config,
            delegator=stub, max_rounds=1,
        )
    )
    results = [r for k, v in events if k == "tool_result" for _, r in (v,)]
    assert results == ["stubbed"]
    assert len(stub.calls) == 1
    assert stub.calls[0].caller_id == "manager"
    assert stub.calls[0].agent_id == "writer"


def test_delegate_tool_outside_harness_explains_itself():
    from kbl.delegator import make_delegate_tool

    tool = make_delegate_tool()
    assert tool.run(agent_id="writer", task="x") == (
        "<delegate> is handled by the harness delegation orchestrator."
    )