"""Stable Diffusion image-generation harness (M7 fork proof #1).

Pure service — must never import Tkinter (guarded by tests/test_purity.py).

A second, drop-in implementation of :class:`kbl.contracts.Harness`, alongside
``kbl.harness.orchestrate``. It reads the last user message as an image
prompt, asks a Stable Diffusion backend for a PNG, saves it under the
workspace (or a cache dir), and yields the standard StreamEvent union — plus
the M7 ``Image`` event carrying the rendered file path.

``StableDiffusionHarness`` is object-based (the protocol's ``__call__`` member
types the plain-function harness; an instance is what the fork swaps in at the
wiring point). The backend call is *injected* via ``backend`` so tests can
substitute a fake and the fork can bind its own SD service; the default is a
minimal AUTOMATIC1111-compatible ``/sdapi/v1/txt2img`` client using only the
stdlib.

The stock text panels ignore ``image`` events (their queue drain has no else
branch), so emitting them can never break the default UI; a ``kbl.contracts.
ImageRenderer`` surface is what actually displays one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterator

from kbl.contracts import StreamEvent, make_stream_event

# Backend contract: (server, model, api_key, prompt, stop_event, steps=None) -> PNG bytes.
ImageBackend = Callable[..., bytes]

DEFAULT_SIZE = 512
DEFAULT_STEPS = 24


def _txt2img_default(
    server,
    model,
    api_key,
    prompt,
    stop_event=None,
    steps: int = DEFAULT_STEPS,
):
    """Minimal AUTOMATIC1111-compatible txt2img client.

    POSTs ``{server}/sdapi/v1/txt2img`` with ``{"prompt", "steps", "width",
    "height"}`` and returns the first generation decoded from base64. ``model``
    is accepted for signature parity with other backends (unused by this one).
    """
    payload = {
        "prompt": prompt,
        "steps": int(steps or DEFAULT_STEPS),
        "width": DEFAULT_SIZE,
        "height": DEFAULT_SIZE,
    }
    request = urllib.request.Request(
        server.rstrip("/") + "/sdapi/v1/txt2img",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    if api_key:
        request.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    images = body.get("images") or []
    if not images:
        raise RuntimeError("SD backend returned no images")
    return base64.b64decode(images[0])


def _last_user_prompt(conversation):
    for message in reversed(list(conversation)):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            prompt = message["content"].strip()
            if prompt:
                return prompt
    return ""


_STEP_RE = re.compile(r"sd_steps")


def _steps_from(config, steps):
    if steps is not None:
        return int(steps)
    if config is not None and isinstance(config.data, dict):
        value = config.data.get("sd_steps") or DEFAULT_STEPS
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULT_STEPS
    return DEFAULT_STEPS


def _slug(server, prompt, steps):
    digest = hashlib.sha256(f"{server}|{prompt}|{steps}".encode("utf-8")).hexdigest()[:8]
    words = re.sub(r"[^A-Za-z0-9]+", "-", prompt.lower()).strip("-")[:40]
    return f"sd_{digest}_{words or 'image'}.png"


def _image_dir(workspace, config, override=None):
    if override is not None:
        base = Path(override)
    elif workspace is not None:
        base = Path(workspace) / ".images"
    elif config is not None and getattr(config, "path", None) is not None:
        base = Path(config.path).parent / "cache"
    else:
        base = Path.home() / ".kbl" / "cache"
    base.mkdir(parents=True, exist_ok=True)
    return base


class StableDiffusionHarness:
    """Object-based :class:`~kbl.contracts.Harness` that renders images.

    Satisfies the ``Harness`` protocol structurally — the same ``__call__``
    surface as ``harness.orchestrate`` — so the M6 wiring point can swap it in
    with no edits inside ``MainWindow`` or ``panels/*``.

    ``backend``: callable ``(server, model, api_key, prompt, stop_event,
    steps=None) -> PNG bytes``; defaults to :func:`_txt2img_default`.
    ``image_dir`` / ``steps`` override the workspace/config resolution.
    """

    def __init__(self, backend: ImageBackend | None = None, image_dir=None, steps=None):
        self._backend = backend if backend is not None else _txt2img_default
        self._image_dir = image_dir
        self._steps = steps

    def __call__(
        self,
        server: str,
        model: str,
        api_key: str,
        conversation: list[dict],
        workspace: Path | None = None,
        config=None,
        stop_event: threading.Event | None = None,
        tools=None,
        system_prompt: str | None = None,
        max_rounds: int | None = None,
        *,
        agent_id: str | None = None,
        depth: int = 0,
        delegator=None,
        event_sink=None,
    ) -> Iterator[StreamEvent]:
        """Run one image generation, yielding a StreamEvent stream.

        Event sequence: ``reasoning``, ``content``, ``tool_call``,
        ``tool_result``, ``image`` (the saved PNG path), ``done`` — or an
        early ``error``/``done`` when the prompt is missing or the backend
        fails. The ``conversation`` list is never mutated.
        """
        prompt = _last_user_prompt(conversation)
        if not prompt:
            yield make_stream_event("error", "No user prompt to render.")
            return
        steps = _steps_from(config, self._steps)

        yield make_stream_event("reasoning", f"Rendering an image for: {prompt[:120]}")
        yield make_stream_event("content", "Generating image\u2026")
        if stop_event is not None and stop_event.is_set():
            yield make_stream_event("done", "Generation stopped.")
            return

        try:
            png = self._backend(server, model, api_key, prompt, stop_event, steps=steps)
        except Exception as exc:
            yield make_stream_event("error", str(exc))
            return
        if stop_event is not None and stop_event.is_set():
            yield make_stream_event("done", "Generation stopped.")
            return

        out_dir = _image_dir(workspace, config, self._image_dir)
        path = out_dir / _slug(server, prompt, steps)
        path.write_bytes(png)

        call = {
            "id": "call_0",
            "name": "render_image",
            "arguments": json.dumps({"prompt": prompt}),
        }
        yield make_stream_event("tool_call", call)
        yield make_stream_event("tool_result", (call, f"image rendered to {path}"))
        yield make_stream_event("image", str(path))
        yield make_stream_event("done", f"Generated image saved to {path}")