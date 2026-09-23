"""Tests for kbl.chat_client: server-agnostic stream+tool-call extraction.

No network access: a fake chat-completions stream object is injected via
``monkeypatch`` on ``_client``.
"""

import threading

from kbl import chat_client


class _FakeDelta:
    def __init__(self, content=None, reasoning=None, tool_calls=None, function_call=None):
        self.content = content
        self.reasoning = reasoning
        self.tool_calls = tool_calls
        self.function_call = function_call


class _FakeChoice:
    def __init__(self, delta):
        self.delta = delta


class _FakeChunk:
    def __init__(self, choices):
        self.choices = choices


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False

    def __iter__(self):
        return iter(self._chunks)

    def close(self):
        self.closed = True


def _fake_client_factory(stream):
    class _FakeCompletions:
        def __init__(self):
            self.created = None

        def create(self, **params):
            self.created = params.get("tools")
            return stream

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    return lambda *a, **k: _FakeClient()


def test_chat_stream_content_and_reasoning(monkeypatch):
    stream = _FakeStream(
        [
            _FakeChunk([_FakeChoice(_FakeDelta(reasoning="think think"))]),
            _FakeChunk([_FakeChoice(_FakeDelta(content="hello "))]),
            _FakeChunk([_FakeChoice(_FakeDelta(content="world"))]),
            _FakeChunk([]),
        ]
    )
    monkeypatch.setattr(chat_client, "_client", _fake_client_factory(stream))
    events = list(chat_client.chat_stream("http://x", "model", []))
    assert events == [("reasoning", "think think"), ("content", "hello "), ("content", "world")]
    assert stream.closed


def test_chat_stream_accumulates_split_tool_calls(monkeypatch):
    tc1 = _FakeDelta(tool_calls=[
        type("TC", (), {"index": 0, "id": "call_1", "function": type("F", (), {"name": "read_file", "arguments": '{"pa'})})(),
        type("TC", (), {"index": 1, "id": "call_2", "function": type("F", (), {"name": "list_files", "arguments": "{}"})})(),
    ])
    tc2 = _FakeDelta(tool_calls=[
        type("TC", (), {"index": 0, "id": None, "function": type("F", (), {"name": "", "arguments": 'th": "a.md"}'})})(),
    ])
    stream = _FakeStream([_FakeChunk([_FakeChoice(tc1)]), _FakeChunk([_FakeChoice(tc2)])])
    monkeypatch.setattr(chat_client, "_client", _fake_client_factory(stream))
    events = list(chat_client.chat_stream("http://x", "model", []))
    assert events == [
        (
            "tool_calls",
            [
                {"id": "call_1", "name": "read_file", "arguments": '{"path": "a.md"}'},
                {"id": "call_2", "name": "list_files", "arguments": "{}"},
            ],
        )
    ]


def test_chat_stream_stop_event(monkeypatch):
    stop = threading.Event()
    stream = _FakeStream([_FakeChunk([_FakeChoice(_FakeDelta(content="a"))])])
    monkeypatch.setattr(chat_client, "_client", _fake_client_factory(stream))
    stop.set()
    events = list(chat_client.chat_stream("http://x", "model", [], stop_event=stop))
    assert events == []


def test_chat_stream_legacy_function_call(monkeypatch):
    stream = _FakeStream(
        [_FakeChunk([_FakeChoice(_FakeDelta(function_call=type("F", (), {"name": "get_current_date", "arguments": "{}"})()))])]
    )
    monkeypatch.setattr(chat_client, "_client", _fake_client_factory(stream))
    events = list(chat_client.chat_stream("http://x", "model", []))
    assert events == [("tool_calls", [{"id": None, "name": "get_current_date", "arguments": "{}"}])]


def test_tools_passed_as_schemas(monkeypatch):
    from kbl.tools import Tool

    tool = Tool("read_file", "d", {"type": "object", "properties": {"path": {"type": "string"}}}, lambda: "")
    stream = _FakeStream([])
    factory = _fake_client_factory(stream)
    monkeypatch.setattr(chat_client, "_client", factory)
    list(chat_client.chat_stream("http://x", "model", [], tools=[tool]))
    assert factory("ignored").chat.completions.created == [tool.to_schema()]


def test_fetch_models_sorted(monkeypatch):
    class _FakeList:
        data = [type("M", (), {"id": "b-model"})(), type("M", (), {"id": "a-model"})()]

    class _FakeModels:
        def list(self):
            return _FakeList()

    class _FakeClient:
        models = _FakeModels()

    monkeypatch.setattr(chat_client, "_client", lambda *a, **k: _FakeClient())
    assert chat_client.fetch_models("http://x") == ["a-model", "b-model"]


def test_fetch_models_wraps_errors(monkeypatch):
    def boom(*a, **k):
        raise ValueError("connection refused")

    monkeypatch.setattr(chat_client, "_client", boom)
    try:
        chat_client.fetch_models("http://x")
        assert False, "expected ServerError"
    except chat_client.ServerError as exc:
        assert "connection refused" in str(exc)