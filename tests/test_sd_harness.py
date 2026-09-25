"""M7: StableDiffusionHarness stream semantics (pure, headless).

Covers: prompt extraction, the event sequence (including the new ``image``
event), backend injection, error and cancellation short-circuits, output file
placement, and the guarantee that ``conversation`` is never mutated.
"""

import threading
from pathlib import Path

from kbl import contracts
from kbl.sd_harness import StableDiffusionHarness, _steps_from

FAKE_PNG = b"\x89PNG\r\n\x1a\nfakepng"


class FakeBackend:
    def __init__(self, png=FAKE_PNG, error=None, set_stop=False):
        self.png = png
        self.error = error
        self.set_stop = set_stop
        self.calls = []

    def __call__(self, server, model, api_key, prompt, stop_event=None, steps=None):
        self.calls.append((server, model, api_key, prompt, stop_event, steps))
        if self.error:
            raise RuntimeError(self.error)
        if self.set_stop and stop_event is not None:
            stop_event.set()
        return self.png


def conversation(*messages):
    return [{"role": "user", "content": m} for m in messages]


def test_emits_full_sequence_including_image(tmp_path):
    backend = FakeBackend()
    harness = StableDiffusionHarness(backend=backend, image_dir=str(tmp_path / "imgs"))

    events = list(
        harness("http://sd:7860", "sd_xl", "k", conversation("a red dragon"))
    )

    assert [e.kind for e in events] == [
        "reasoning",
        "content",
        "tool_call",
        "tool_result",
        "image",
        "done",
    ]
    image_event = events[4]
    assert isinstance(image_event, contracts.Image)
    path = Path(image_event.path)
    assert path.exists() and path.read_bytes() == FAKE_PNG
    assert path.suffix == ".png"
    assert events[3].payload[1] == f"image rendered to {path}"
    assert backend.calls[0][3] == "a red dragon"


def test_uses_last_non_empty_user_prompt(tmp_path):
    backend = FakeBackend()
    harness = StableDiffusionHarness(backend=backend, image_dir=str(tmp_path))
    list(
        harness(
            "s",
            "m",
            "k",
            [{"role": "user", "content": "first"}, {"role": "user", "content": "latest"}],
        )
    )
    assert backend.calls[0][3] == "latest"

    backend2 = FakeBackend()
    list(
        StableDiffusionHarness(backend=backend2, image_dir=str(tmp_path))(
            # trailing empty user message falls back to an earlier prompt
            "s",
            "m",
            "k",
            [{"role": "user", "content": "keep me"}, {"role": "user", "content": "  "}],
        )
    )
    assert backend2.calls[0][3] == "keep me"


def test_no_user_prompt_yields_error():
    events = list(StableDiffusionHarness()("s", "m", "k", [{"role": "system", "content": "x"}]))
    assert events[0].kind == "error"
    assert "No user prompt" in events[0].message


def test_backend_failure_yields_error():
    backend = FakeBackend(error="backend exploded")
    events = list(StableDiffusionHarness(backend=backend)("s", "m", "k", conversation("x")))
    assert events[-1].kind == "error"
    assert "backend exploded" in events[-1].message


def test_stop_event_before_backend_short_circuits(tmp_path):
    backend = FakeBackend(set_stop=False)
    stop = threading.Event()
    stop.set()
    harness = StableDiffusionHarness(backend=backend, image_dir=str(tmp_path))
    events = list(harness("s", "m", "k", conversation("x"), stop_event=stop))
    assert [e.kind for e in events] == ["reasoning", "content", "done"]
    assert events[-1].text == "Generation stopped."
    assert backend.calls == []


def test_stop_event_set_during_backend_short_circuits(tmp_path):
    stop = threading.Event()
    backend = FakeBackend(set_stop=True)
    events = list(
        StableDiffusionHarness(backend=backend, image_dir=str(tmp_path))(
            "s", "m", "k", conversation("x"), stop_event=stop
        )
    )
    assert [e.kind for e in events] == ["reasoning", "content", "done"]
    assert events[-1].text == "Generation stopped."


def test_conversation_is_never_mutated(tmp_path):
    convo = conversation("a red dragon")
    snapshot = list(convo)
    list(StableDiffusionHarness(image_dir=str(tmp_path))("s", "m", "k", convo))
    assert convo == snapshot


def test_steps_read_from_config_when_not_injected(tmp_path):
    config = type("C", (), {"data": {"sd_steps": 8}, "path": tmp_path / "config.json"})()
    assert _steps_from(config, None) == 8
    assert _steps_from(config, 4) == 4
    assert _steps_from(None, None) == 24
    assert _steps_from(type("C", (), {"data": {"sd_steps": "banana"}})(), None) == 24


def test_image_dir_argument_wins(tmp_path):
    backend = FakeBackend()
    harness = StableDiffusionHarness(backend=backend, image_dir=str(tmp_path / "out"))
    events = list(harness("s", "m", "k", conversation("clouds")))
    path = Path(events[4].path)
    assert path.parent == tmp_path / "out"
    assert path.exists()


def test_workspace_uses_dot_images_dir(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    harness = StableDiffusionHarness(backend=FakeBackend(), image_dir=None)
    events = list(harness("s", "m", "k", conversation("clouds"), workspace=workspace))
    path = Path(events[4].path)
    assert path.parent == workspace / ".images"
    assert path.exists()