"""M2: the contract surface (kbl.contracts) + the components that satisfy it.

Covers: contracts.py imports cleanly standalone; StreamEvent construction;
structural isinstance checks that the real components satisfy their
Protocols (Harness -> kbl.harness.orchestrate, DisplayRenderer ->
kbl.markdown_render.MarkdownRenderer).
"""

import ast
import importlib
import pathlib

import kbl
from kbl import contracts, harness, markdown_render

# ---------------------------------------------------------------------------
# contracts.py standalone.
# ---------------------------------------------------------------------------


def test_contracts_imports_standalone():
    module = importlib.import_module("kbl.contracts")
    assert module.StreamEvent is not None


def test_contracts_module_has_no_tkinter_import():
    root = pathlib.Path(kbl.__file__).parent
    tree = ast.parse((root / "contracts.py").read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    assert "tkinter" not in imports
    assert "ttkbootstrap" not in imports


# ---------------------------------------------------------------------------
# StreamEvent construction.
# ---------------------------------------------------------------------------


def test_make_stream_event_round_trips_every_kind():
    cases = [
        ("content", "hi "),
        ("reasoning", "think"),
        ("tool_call", {"id": "call_1", "name": "read_file", "arguments": "{}"}),
        ("tool_result", ({"id": "call_1"}, "the file")),
        ("done", "hi"),
        ("error", "boom"),
        ("image", "/tmp/kbl/generated.png"),
    ]
    for kind, payload in cases:
        event = contracts.make_stream_event(kind, payload)
        assert event.kind == kind
        assert event == (kind, payload)


def test_make_stream_event_subclassed_by_kind():
    event = contracts.make_stream_event("tool_call", {})
    assert isinstance(event, contracts.ToolCall)
    event = contracts.make_stream_event("done", "x")
    assert isinstance(event, contracts.Done)
    assert isinstance(event, contracts.StreamEvent)


def test_make_stream_event_rejects_unknown_kind():
    import pytest

    with pytest.raises(ValueError):
        contracts.make_stream_event("wibble", None)


# ---------------------------------------------------------------------------
# Harness contract satisfied by kbl.harness.orchestrate.
# ---------------------------------------------------------------------------


def test_harness_protocol_satisfied_by_orchestrate():
    assert isinstance(harness.orchestrate, contracts.Harness)


def test_harness_protocol_exposes_the_sync_signature():
    sig = contracts.Harness.__call__
    params = list(sig.__annotations__)
    assert params[0] == "server"
    assert params[1] == "model"
    assert params[2] == "api_key"
    assert "stop_event" in params
    assert "conversation" in params


# ---------------------------------------------------------------------------
# DisplayRenderer contract satisfied by MarkdownRenderer.
# ---------------------------------------------------------------------------


def test_display_renderer_protocol_satisfied_by_markdown_renderer():
    renderer = markdown_render.MarkdownRenderer()
    assert isinstance(renderer, contracts.DisplayRenderer)


def test_display_renderer_has_the_three_operations():
    renderer = markdown_render.MarkdownRenderer()
    for name in ("setup", "render", "append"):
        assert callable(getattr(renderer, name))


# ---------------------------------------------------------------------------
# M7 fork-proof drop-ins satisfy the contracts.
# ---------------------------------------------------------------------------


def test_stable_diffusion_harness_satisfies_harness_protocol():
    from kbl.sd_harness import StableDiffusionHarness

    for instance in (StableDiffusionHarness(), StableDiffusionHarness(backend=lambda **kw: b"")):
        assert isinstance(instance, contracts.Harness)


def test_tk_image_renderer_satisfies_image_renderer_protocol():
    from kbl.image_render import TkImageRenderer

    renderer = TkImageRenderer()
    assert isinstance(renderer, contracts.ImageRenderer)
    for name in ("setup", "render"):
        assert callable(getattr(renderer, name))


def test_image_event_is_a_stream_event_variant():
    event = contracts.make_stream_event("image", "/tmp/x.png")
    assert isinstance(event, contracts.Image)
    assert isinstance(event, contracts.StreamEvent)
    assert event == ("image", "/tmp/x.png")


# ---------------------------------------------------------------------------
# Contracts are pure value/description modules: protocols only.
# ---------------------------------------------------------------------------


def test_forward_contracts_are_protocols():
    for name in (
        "ToolRegistry",
        "FileRepository",
        "EventBus",
        "Agent",
        "AgentRegistry",
        "SubagentRegistry",
        "Delegator",
    ):
        assert issubclass(getattr(contracts, name), contracts.Protocol), name


def test_runtime_contracts_are_runtime_checkable():
    for name in (
        "Harness",
        "DisplayRenderer",
        "ImageRenderer",
        "Device",
        "WorkspaceProvider",
        "ConfigStore",
        "ToolCollection",
    ):
        cls = getattr(contracts, name)
        assert cls._is_protocol and cls._is_runtime_protocol, name


def test_delegation_request_is_a_typed_dataclass():
    req = contracts.DelegationRequest(
        caller_id="assistant",
        agent_id="writer",
        task="draft",
        context=[{"role": "user", "content": "x"}],
        tool_allowlist={"read_file"},
    )
    assert req.caller_id == "assistant"
    assert req.agent_id == "writer"
    assert req.task == "draft"
    assert req.context == [{"role": "user", "content": "x"}]
    assert req.tool_allowlist == {"read_file"}
    assert req == req  # frozen + dataclass equality


def test_delegation_result_is_a_typed_dataclass():
    result = contracts.DelegationResult(task_id="t_1", result="draft text", tool_calls=[{"id": "c"}])
    assert result.task_id == "t_1"
    assert result.result == "draft text"
    assert result.tool_calls == [{"id": "c"}]
    assert contracts.DelegationResult(task_id="t", result="").tool_calls is None


def test_subagent_delegator_satisfies_delegator_protocol():
    """Structural check: the standing impl exposes the Delegator surface."""
    from kbl.delegator import SubagentDelegator

    delegator = SubagentDelegator(config=None)
    assert callable(getattr(delegator, "delegate"))
    import inspect

    params = inspect.signature(SubagentDelegator.delegate).parameters
    assert "request" in params and "stop_event" in params
    assert "depth" in params  # harness passes nesting level