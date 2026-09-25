# M7 mini-plan — fork-proof contract extension scope

Date: 2026-09-25 · Status: scoped before M7 implementation (roadmap M7, step 2)

## Goal of the extension

M7 proves the M6 seams with two drop-in swaps (roadmap M7):

1. `harness` → an object-based **`StableDiffusionHarness`** in `kbl/sd_harness.py`
   (satisfies `contracts.Harness`, plays through the same wiring as
   `kbl.harness.orchestrate`).
2. `markdown_render` → an image-capable **`TkImageRenderer`** in
   `kbl/image_render.py` implementing a distinct `ImageRenderer` protocol.

The roadmap explicitly flags that the current `Device` surface and the
`StreamEvent` text payloads assume a `Text`-like widget, and asks that the
extension ("a distinct image-renderer protocol and/or an image stream event")
be **scoped as a mini-plan first**. This document is that scope.

## Decisions

### 1. One new StreamEvent variant: `Image`

- `contracts.Image(kind="image", path: str)` — payload is the rendered image
  file path (a string, matching how other payloads are plain values).
- Added to the `StreamEvent` union and to `make_stream_event`'s `_STREAM_KINDS`
  registry, so `make_stream_event("image", path)` round-trips under the same
  `event == ("image", path)` invariant as every other kind. **No existing
  variant changes.**

Justification (narrow): the "and/or" in the roadmap → an image *event* is the
minimal extension a harness needs to *report* a generated image through the
standard stream. We add a distinct image-*renderer* protocol too (decision 2)
so the fork's panel can *display* it.

### 2. One new protocol: `ImageRenderer` (distinct from `DisplayRenderer`)

```python
@runtime_checkable
class ImageRenderer(Protocol):
    def setup(self, device) -> None: ...
    def render(self, device, image) -> None: ...
```

- `DisplayRenderer` is intentionally **unchanged**; a text markdown renderer
  must not be forced to carry image methods, and the M6 seam (`renderer=`)
  stays text-shaped.
- `Device` stays Text-like and **unchanged**. The fork's image surface
  (its `ImageCanvas`) is not described here; `TkImageRenderer` works with
  whichever surface is handed to it and degrades gracefully to a text
  placeholder on a Text-like device.

### 3. Zero edits inside `panels/*` or `MainWindow`

Verified by reading the current dispatch: `ChatPanel._drain_queue`
(`kbl/panels/chat.py:397-417`) handles `reasoning/content/tool_call/tool_result/
done/error` and subagent topics with **no `else` branch**, so an unknown kind
(here `"image"`) is silently skipped. Consequences:

- Swapping in `StableDiffusionHarness` cannot break the stock panels — it can
  emit `image` freely; the current UI simply renders the accompanying
  `content`/`done` text.
- *Displaying* images is the fork's `ImageCanvas` panel, which consumes the new
  `ImageRenderer` protocol. This repo proves the **seam** (protocol satisfaction
  + drop-in composition), not the fork's UI.
- The swap itself remains a **wiring argument change** at `MainWindow._build_panels`
  (`harness=harness.orchestrate` → `harness=StableDiffusionHarness(backend=...)`,
  and the renderer parameter) — exactly the M6 "single wiring point". A static
  test (`tests/test_fork_proof.py`) enforces that `kbl/sd_harness.py` and
  `kbl/image_render.py` are never referenced by `panels/*` or `main_window.py`.

### 4. Harness backend is injected, not hardwired

`StableDiffusionHarness(backend=None, image_dir=None, steps=None)`:

- `backend` is a callable `(server, model, api_key, prompt, stop_event, steps=None) -> bytes`
  (PNG bytes). Default is a minimal AUTOMATIC1111-compatible client
  (`POST {server}/sdapi/v1/txt2img`, base64-decodes `images[0]`) using only the
  stdlib (`urllib`) — **no new dependencies**.
- Tests inject a fake backend (headless, offline). The fork binds its real SD
  service here. The harness stays a pure service (`sd_harness` joins
  `PURE_SERVICES` in `tests/test_purity.py`).

### 5. Where generated images land

- Workspace present → `<workspace>/.images/<slug>.png` (per-workspace cache).
- No workspace → `<~/.kbl>/cache/<slug>.png` (derived from `config.path.parent`,
  falling back to `~/.kbl/cache` when `config` is `None`).
- Filename slug is deterministic from `(server, prompt, steps)` so a repeated
  prompt replaces, never piles up.

## Test surface

| File | Addition |
|---|---|
| `tests/test_contracts.py` | `image` in `make_stream_event` round-trip; `ImageRenderer` in the runtime-checkable list; `isinstance(StableDiffusionHarness(), Harness)`; `isinstance(TkImageRenderer(), ImageRenderer)` |
| `tests/test_sd_harness.py` (new) | event-kind sequence; prompt extraction; no-user-message → `error`; backend failure → `error`; stop_event short-circuits before/after backend; conversation not mutated; steps read from `config.data["sd_steps"]` |
| `tests/test_purity.py` | `sd_harness` added to `PURE_SERVICES` |
| `tests/test_fork_proof.py` (new) | AST scan: `panels/*` + `main_window.py` never import `kbl.sd_harness`/`kbl.image_render`; each drop-in satisfies its contract; the swap lines exist at the wiring point |

## Exclusions (out of scope for M7)

- No `asyncio`, no new third-party deps, no `Device`/`DisplayRenderer` reshaping.
- No routing of `image` events inside the stock panels (deliberate per decision 3).
- No changes to `main_window.py`'s code; the wiring *call sites* are the fork's
  edit surface.