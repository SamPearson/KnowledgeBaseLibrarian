"""OpenAI-compatible chat client for Ollama and llama.cpp servers.

Both servers expose the OpenAI chat completions API at `<server>/chat/completions`
and the model list at `<server>/models`, so a single client (the `openai`
package) works against either. The user-entered server URL is used as the
base_url; api_key is optional (local servers ignore it).
"""

DEFAULT_API_KEY = "not-needed"
TIMEOUT_SECONDS = 60


class ServerError(Exception):
    """Raised when the server can't be reached or returns an error."""


def _client(server_url, api_key="", timeout=TIMEOUT_SECONDS):
    from openai import OpenAI

    return OpenAI(
        api_key=(api_key or "").strip() or DEFAULT_API_KEY,
        base_url=server_url,
        timeout=timeout,
    )


def fetch_models(server_url, api_key="", timeout=5):
    """Return a sorted list of model ids from the server, or raise ServerError."""
    try:
        response = _client(server_url, api_key, timeout=timeout).models.list()
    except Exception as exc:
        raise ServerError(str(exc)) from exc
    return sorted(model.id for model in response.data)


def chat_stream(server_url, model, messages, api_key="", stop_event=None, tools=None):
    """Yield ("reasoning"|"content", text|("tool_calls", calls)) deltas.

    Qwen3-style models first produce a reasoning/thinking phase (exposed via
    the non-standard `delta.reasoning` field) before the real answer in
    `delta.content`; reasoning and content are mutually exclusive per chunk.

    When the model emits tool calls, their chunks are accumulated per index and
    yielded once, after the stream ends, as a single
    ``("tool_calls", calls)`` event where each call is
    ``{"id", "name", "arguments"}`` with ``arguments`` a JSON string.

    The caller stops consuming (or sets stop_event) to abort the in-flight
    request; the underlying connection is closed on exit.
    """
    params = dict(model=model, messages=messages, stream=True)
    if tools:
        params["tools"] = [t.to_schema() if hasattr(t, "to_schema") else t for t in tools]
    stream = _client(server_url, api_key).chat.completions.create(**params)
    tool_calls = {}
    try:
        for chunk in stream:
            if stop_event is not None and stop_event.is_set():
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if not delta:
                continue
            reasoning = getattr(delta, "reasoning", None)
            if reasoning:
                yield ("reasoning", reasoning)
            if delta.content:
                yield ("content", delta.content)
            for tc in getattr(delta, "tool_calls", None) or []:
                index = tc.index if tc.index is not None else 0
                call = tool_calls.setdefault(index, {"id": None, "name": "", "arguments": ""})
                if tc.id:
                    call["id"] = tc.id
                if tc.function and tc.function.name:
                    call["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    call["arguments"] += tc.function.arguments
            fc = getattr(delta, "function_call", None)
            if fc:
                call = tool_calls.setdefault(0, {"id": None, "name": "", "arguments": ""})
                if fc.name:
                    call["name"] = fc.name
                if fc.arguments:
                    call["arguments"] += fc.arguments
    finally:
        try:
            stream.close()
        except Exception:
            pass
    if tool_calls:
        yield ("tool_calls", [tool_calls[i] for i in sorted(tool_calls)])