"""OpenAI-compatible chat client for Ollama and llama.cpp servers.

Both servers expose the OpenAI chat completions API at `<server>/chat/completions`
and the model list at `<server>/models`, so a single client (the `openai`
package) works against either. The user-entered server URL is used as the
base_url; api_key is optional (local servers ignore it).
"""

import threading

DEFAULT_API_KEY = "not-needed"
TIMEOUT_SECONDS = 60

# Guarantees exactly one in-flight stream per process; Set() aborts it.
_STOP = threading.Event()


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


def chat_stream(server_url, model, messages, api_key="", stop_event=None):
    """Yield ("reasoning"|"content", text) deltas for a chat completion.

    Qwen3-style models first produce a reasoning/thinking phase (exposed via
    the non-standard `delta.reasoning` field) before the real answer in
    `delta.content`; reasoning and content are mutually exclusive per chunk.
    The caller stops consuming (or sets stop_event) to abort the in-flight
    request; the underlying connection is closed on exit.
    """
    stream = _client(server_url, api_key).chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
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
    finally:
        try:
            stream.close()
        except Exception:
            pass