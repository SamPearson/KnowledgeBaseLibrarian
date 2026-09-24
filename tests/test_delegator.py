"""M5: the delegation orchestrator (kbl.delegator).

Unit coverage for ``SubagentDelegator``, ``invoke_delegate``,
``make_delegate_tool``, and the config fallback, using a stub ``run_agent`` so
no network or harness recursion is involved. The harness-level integration
(delegate tool calls intercepted inside orchestrate, allowlist intersection)
lives in test_harness.py.
"""

import threading

from kbl import agents
from kbl.delegator import (
    DEFAULT_MAX_DELEGATED_TURNS,
    DELEGATE_TOOL_NAME,
    SubagentDelegator,
    invoke_delegate,
    make_delegate_tool,
    max_delegated_turns,
)
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

from kbl.contracts import DelegationRequest, make_stream_event


def _make_agents(kbl_dirs):
    """Create a manager who may delegate to a writer with default caps."""
    agents.create_agent("manager")
    manager = agents.load_agent("manager")
    manager.can_delegate_to = ["writer"]
    agents.save_metadata("manager", manager)
    agents.create_agent("writer")
    return agents.load_agent("manager"), agents.load_agent("writer")


def _fake_run_agent(events, log=None):
    def run(config, workspace, conversation, stop_event, *, agent_id, depth, max_rounds, allowlist):
        if log is not None:
            log.append(
                {
                    "conversation": list(conversation),
                    "agent_id": agent_id,
                    "depth": depth,
                    "max_rounds": max_rounds,
                    "allowlist": allowlist,
                }
            )
        for event in events:
            if isinstance(event, tuple) and event and isinstance(event[0], str):
                yield make_stream_event(*event)
            else:
                yield event

    return run


def _sink_log():
    entries = []

    def sink(kind, payload):
        entries.append((kind, payload))

    return sink, entries


def _request(caller_id="manager", agent_id="writer", **overrides):
    return DelegationRequest(
        caller_id=overrides.pop("caller_id", caller_id),
        agent_id=overrides.pop("agent_id", agent_id),
        task=overrides.pop("task", "draft the brief"),
        context=overrides.pop("context", []),
        tool_allowlist=overrides.pop("tool_allowlist", None),
        **overrides,
    )


# ---------------------------------------------------------------------------
# max_delegated_turns fallback.
# ---------------------------------------------------------------------------


def test_max_delegated_turns_defaults():
    assert max_delegated_turns(None) == DEFAULT_MAX_DELEGATED_TURNS

    class C:
        data = {"max_delegated_turns": 12}

    assert max_delegated_turns(C()) == 12

    for bad in ({"max_delegated_turns": "abc"}, {"max_delegated_turns": 0}):

        class B:
            data = bad

        assert max_delegated_turns(B()) == DEFAULT_MAX_DELEGATED_TURNS


# ---------------------------------------------------------------------------
# make_delegate_tool / invoke_delegate.
# ---------------------------------------------------------------------------


def test_make_delegate_tool_schema():
    tool = make_delegate_tool()
    assert tool.name == DELEGATE_TOOL_NAME
    fn = tool.to_schema()["function"]
    assert fn["parameters"]["required"] == ["agent_id", "task"]
    props = fn["parameters"]["properties"]
    assert set(props) == {"agent_id", "task", "context", "tool_allowlist"}
    assert tool.run(agent_id="writer", task="x") == (
        "<delegate> is handled by the harness delegation orchestrator."
    )


def test_invoke_delegate_parses_the_call():
    seen = {}

    class Fake:
        def delegate(self, request, stop_event=None, depth=0):
            seen["request"] = request
            seen["depth"] = depth
            from kbl.contracts import DelegationResult

            return DelegationResult(task_id="t1", result="child result")

    call = {
        "id": "call_1",
        "name": "delegate",
        "arguments": '{"agent_id": "writer", "task": "draft", '
        '"context": [{"role": "user", "content": "x"}], '
        '"tool_allowlist": ["read_file"]}',
    }
    result = invoke_delegate(Fake(), call, "manager", depth=2)
    assert result == "child result"
    req = seen["request"]
    assert req.caller_id == "manager"
    assert req.agent_id == "writer"
    assert req.task == "draft"
    assert req.context == [{"role": "user", "content": "x"}]
    assert req.tool_allowlist == {"read_file"}
    assert seen["depth"] == 2


def test_invoke_delegate_returns_error_strings_for_bad_calls():
    class Fake:
        def delegate(self, request, stop_event=None, depth=0):
            raise AssertionError("should not be called")

    assert invoke_delegate(Fake(), {"arguments": "not json"}, "m") == "delegate: could not parse arguments"
    assert invoke_delegate(Fake(), {"arguments": "[1, 2]"}, "m") == "delegate: arguments must be an object"
    assert (
        invoke_delegate(Fake(), {"arguments": '{"task": "draft"}'}, "m")
        == "delegate: agent_id and task are required"
    )


# ---------------------------------------------------------------------------
# SubagentDelegator happy path.
# ---------------------------------------------------------------------------


def test_delegate_runs_scoped_subagent(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    manager = agents.load_agent("manager")
    writer = agents.load_agent("writer")
    run_log = []
    sink, entries = _sink_log()
    delegator = SubagentDelegator(
        tmp_config,
        workspace="/tmp/ws",
        event_sink=sink,
        run_agent=_fake_run_agent(
            [("content", "the "), ("content", "brief"), ("done", "the brief")],
            log=run_log,
        ),
    )
    result = delegator.delegate(_request())
    assert result.task_id
    assert result.result == "the brief"
    assert delegator._used_turns == int(writer.max_turns)

    ran = run_log[0]
    assert ran["agent_id"] == "writer"
    assert ran["depth"] == 1
    assert ran["max_rounds"] == int(writer.max_turns)
    assert ran["allowlist"] is None
    assert ran["conversation"] == [
        {"role": "user", "content": "draft the brief"}
    ]

    kinds = [k for k, _ in entries]
    assert kinds == [
        DELEGATION_REQUESTED,
        SUBAGENT_STARTED,
        SUBAGENT_EVENT,
        SUBAGENT_EVENT,
        SUBAGENT_COMPLETED,
    ]
    requested = entries[0][1]
    assert isinstance(requested, DelegationRequested)
    assert requested.caller_id == "manager"
    assert requested.agent_id == "writer"
    assert requested.task == "draft the brief"
    assert requested.context == []
    assert requested.tool_allowlist is None

    started = entries[1][1]
    completed = entries[4][1]
    assert isinstance(started, SubagentStarted)
    assert isinstance(completed, SubagentCompleted)
    assert started.task_id == result.task_id
    assert completed.task_id == result.task_id
    assert completed.result == "the brief"
    assert completed.tool_calls is None
    for _, payload in entries[2:4]:
        assert payload.task_id == result.task_id


def test_delegate_passes_context_and_allowlist_through(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    run_log = []
    delegator = SubagentDelegator(
        tmp_config,
        event_sink=None,
        run_agent=_fake_run_agent([("done", "ok")], log=run_log),
    )
    delegator.delegate(
        _request(
            context=[{"role": "user", "content": "pre"}],
            tool_allowlist={"read_file", "list_files"},
        )
    )
    ran = run_log[0]
    assert ran["conversation"] == [
        {"role": "user", "content": "pre"},
        {"role": "user", "content": "draft the brief"},
    ]
    assert ran["allowlist"] == {"read_file", "list_files"}


def test_delegate_collects_child_tool_calls(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    call = {"id": "c1", "name": "read_file", "arguments": '{"path": "a.md"}'}
    delegator = SubagentDelegator(
        tmp_config,
        event_sink=sink,
        run_agent=_fake_run_agent(
            [
                ("tool_call", call),
                ("tool_result", (call, "# A")),
                ("content", "done"),
                ("done", "done"),
            ]
        ),
    )
    result = delegator.delegate(_request())
    assert result.tool_calls == [call]
    completed = entries[-1][1]
    assert completed.tool_calls == [call]


# ---------------------------------------------------------------------------
# SubagentDelegator failure paths.
# ---------------------------------------------------------------------------


def test_delegate_unknown_caller_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=_fake_run_agent([]))
    result = delegator.delegate(_request(caller_id="ghost"))
    assert result.result == "delegate: caller agent not found"
    assert _all_failed(entries)


def test_delegate_unknown_child_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=_fake_run_agent([]))
    result = delegator.delegate(_request(agent_id="ghost"))
    assert result.result == "delegate: agent 'ghost' not found"
    assert _all_failed(entries)


def test_delegate_not_in_can_delegate_to_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=_fake_run_agent([]))
    result = delegator.delegate(_request(agent_id="manager"))
    assert result.result == "delegate: agent 'manager' is not in 'manager's can_delegate_to list"
    assert _all_failed(entries)


def test_delegate_depth_cap_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    writer = agents.load_agent("writer")
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=_fake_run_agent([]))
    result = delegator.delegate(_request(), depth=int(writer.max_depth))
    assert result.result == f"delegate: max nesting depth {writer.max_depth} reached"
    assert _all_failed(entries)


def test_delegate_turn_budget_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    tmp_config.data["max_delegated_turns"] = 4
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=_fake_run_agent([]))
    result = delegator.delegate(_request())
    assert result.result == "delegate: delegated turn budget exhausted"
    assert _all_failed(entries)


def test_delegate_budget_accumulates_across_children(kbl_dirs, tmp_config):
    agents.create_agent("manager")
    manager = agents.load_agent("manager")
    manager.can_delegate_to = ["writer", "reader"]
    agents.save_metadata("manager", manager)
    agents.create_agent("writer")
    agents.create_agent("reader")
    tmp_config.data["max_delegated_turns"] = 12
    delegator = SubagentDelegator(
        tmp_config, event_sink=None, run_agent=_fake_run_agent([("content", "ok"), ("done", "ok")])
    )
    first = delegator.delegate(_request(agent_id="writer"))
    assert first.result == "ok"
    blocked = delegator.delegate(_request(agent_id="reader"))
    assert blocked.result == "delegate: delegated turn budget exhausted"


def test_delegate_without_runner_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink)
    result = delegator.delegate(_request())
    assert result.result == "delegate: subagent runner unavailable"
    assert _all_failed(entries)


def test_delegate_child_error_event_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)
    sink, entries = _sink_log()
    delegator = SubagentDelegator(
        tmp_config,
        event_sink=sink,
        run_agent=_fake_run_agent([("error", "no such file")]),
    )
    result = delegator.delegate(_request())
    assert result.result == "no such file"
    assert _all_failed(entries)


def test_delegate_child_exception_fails(kbl_dirs, tmp_config):
    _make_agents(kbl_dirs)

    def boom(*a, **k):
        raise RuntimeError("boom")

    sink, entries = _sink_log()
    delegator = SubagentDelegator(tmp_config, event_sink=sink, run_agent=boom)
    result = delegator.delegate(_request())
    assert result.result == "delegate failed: boom"
    assert _all_failed(entries)


def _all_failed(entries):
    return (
        any(k == SUBAGENT_FAILED for k, _ in entries)
        and all(not (k == SUBAGENT_COMPLETED) for k, _ in entries)
        and all(payload.task_id for _, payload in entries if hasattr(payload, "task_id"))
    )