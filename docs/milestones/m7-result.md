# M7 — Fork proof (two drop-in swaps)

Status: **complete** (2026-09-25)

## Goal

Prove the M6 seams with two drop-in swaps, per the roadmap's plan: a **second
harness** (`StableDiffusionHarness`, an image-generation backend) and a
**second display type** (an image-capable renderer for the fork's future
`ImageCanvas`). The requirement: swapping either in requires no edits inside
`MainWindow` or `panels/*` — only the wiring arguments change.

This milestone was scoped in `docs/milestones/m7-mini-plan.md` before any code
changed, per the roadmap's instruction.

## What changed

### 1. Narrow contract extension (`kbl/contracts.py`)

The existing `Device` surface (`cget`/`tag_configure`/`configure`/`delete`/
`insert`) and the `DisplayRenderer` text payload were left **unchanged**. Two
additions only:

- **`Image` stream event** — `NamedTuple(kind="image", path: str)` describing
  a rendered image file, added to the `StreamEvent` union and the
  `_STREAM_KINDS` registry, so `make_stream_event("image", path)` round-trips
  from any producer:
  ```
  class Image(NamedTuple):
      kind: Literal["image"] = "image"
      path: str = ""
  ```
- **`ImageRenderer`** — a distinct, runtime-checkable protocol next to
  `DisplayRenderer`:
  ```
  @runtime_checkable
  class ImageRenderer(Protocol):
      def setup(self, device) -> None: ...
      def render(self, device, image) -> None: ...
  ```

The text stream and the existing contracts are untouched, so M0–M6 behavior is
unchanged.

### 2. Second harness: `kbl/sd_harness.py` (new, pure service)

`StableDiffusionHarness` implements `Harness` (structural `isinstance` passes
without importing the protocol). It reads the **last non-empty user message**
as the image prompt, asks a pluggable backend for PNG bytes, saves the result,
and streams the standard event union **plus** the new `Image` event:

`reasoning → content → tool_call("render_image") → tool_result → image →
done`

- **Backend is injected**: `StableDiffusionHarness(backend=None, image_dir=None,
  steps=None)`. The default backend is a minimal AUTOMATIC1111-compatible
  client (`POST {server}/sdapi/v1/txt2img`, `Authorization: Bearer` when an
  API key is configured, stdlib `urllib` only — no new dependencies). Tests
  inject a fake backend, so the harness is fully exercisable headlessly.
- **Output placement**: workspace → `<workspace>/.images/<slug>.png`; config
  present → `<config dir>/cache/`; otherwise `~/.kbl/cache/`. Filenames derive
  from `sha256(server|prompt|steps)` for reproducibility.
- **Cancellation**: `stop_event` is honored both before and after the backend
  call, yielding `done("Generation stopped.")` and short-circuiting.
- **Failure**: backend errors surface as `error` events; an empty
  conversation yields `error("No user prompt to render.")`.
- **Pure**: no Tkinter import (`sd_harness` added to `PURE_SERVICES` in
  `tests/test_purity.py`).
- `conversation` is never mutated.

### 3. Second display: `kbl/image_render.py` (new, view layer)

`TkImageRenderer` structurally satisfies `ImageRenderer`. It draws onto a
canvas-like surface (`delete`/`create_image`), scaling the photo to fit the
canvas width and pinning `device._last_photo` so Tk doesn't garbage-collect the
image. A Text-like surface without `create_image` degrades to a
`🖼 Image: <path>` tag-styled line. Tkinter is imported lazily inside methods,
so the module imports headlessly (mirroring `markdown_render`).

### 4. Wiring: proven to be argument-only

The stock UI (Text markdown stream) keeps `harness.orchestrate` +
`MarkdownRenderer`. Swapping is editing the two wiring arguments in
`MainWindow._build_panels`:

```python
ChatPanel(..., harness=StableDiffusionHarness(), renderer=ImageRenderer())
```

`ChatPanel._drain_queue` dispatches on event kind and has **no else branch**, so
an `image` event is silently ignored by the text UI while its accompanying
`content`/`done` text still renders — the fork's `ImageCanvas` panel is the one
that consumes `Image` events via `ImageRenderer`. No code inside `MainWindow` or
`panels/*` changed for M7.

### 5. Tests

- `tests/test_contracts.py`: `image` added to the round-trip cases;
  `ImageRenderer` added to the runtime-checkable list; new tests assert
  `StableDiffusionHarness` satisfies `Harness`, `TkImageRenderer` satisfies
  `ImageRenderer`, and `Image` is a `StreamEvent` variant.
- `tests/test_sd_harness.py` (new, 11 tests): full event sequence, prompt
  extraction, backend failure, both cancellation paths, mutation-free
  conversation, steps-from-config, and both output-placement rules.
- `tests/test_fork_proof.py` (new): AST-scans every `kbl/panels/*.py` **and**
  `main_window.py` to enforce they never import `sd_harness`/`image_render`;
  asserts the documented swap-site arguments exist (`harness=harness.orchestrate`,
  `renderer=renderer` in `main_window.py`; `harness=None`/`renderer=None` seam
  defaults in `chat.py`); and asserts both drop-ins satisfy their contracts
  (the "swap it in and it gleams" gate).

## Verification

- `venv/bin/python -m pytest tests/ -q` → **207 passed** in 0.73s
  (190 pre-M7 + 17 new: 11 harness + 4 fork-proof + 3 contracts, with the
  image round-trip folded into existing tests).
- No edits inside `kbl/panels/*` or `kbl/main_window.py` this milestone.

## Deliberately not done (scoped out in the mini-plan)

- **No async/threading changes**, no new dependencies, no reshaping of
  `Device` to an abstract canvas protocol. `ImageRenderer` is the promised
  narrow extension; a fuller `ImageCanvas`/`Device` generalization is the
  fork's call, on top of a seam that now demonstrably accepts it.
- The stock GUI does **not** render inline images — the `Image` event's display
  path is the fork's `ImageCanvas`, by design.

## Acceptance check

> Swapping `harness`→`StableDiffusionHarness` (or `markdown_render`→
> `ImageRenderer`) requires no edits inside `MainWindow` or `panels/*`.

Enforced mechanically by `tests/test_fork_proof.py` (import scan + contract
satisfaction). The seam can now absorb a folder, a GPU box, or a canvas — the
milestones exist so the fork edits exactly one place.