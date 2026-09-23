# M2 — contracts.py + DisplayRenderer

Status: **complete** (2026-09-23)

## Goal

The contract surface from `system_architecture.md` section 5 exists — as
**synchronous** `Protocol`s, per the locked-in concurrency model — and the two
real seams (`harness`, `markdown_render`) are structurally bound to it so they
can be swapped at fork time (M6).

## What changed

- **New `kbl/contracts.py`** (pure service, zero Tkinter; stdlib only):
  - `StreamEvent` union — `Content | Reasoning | ToolCall | ToolResult | Done | Error`
    as `NamedTuple` variants, so each event still *is* a `(kind, payload)`
    tuple and the panel's queue drain (`kind, value = queue.get_nowait()`)
    keeps working unchanged. `make_stream_event(kind, payload)` is the only
    constructor; unknown kinds raise `ValueError`.
  - `Harness` — a `runtime_checkable` `Protocol` typing `__call__` with the
    **actual** `harness.orchestrate` signature, returning
    `Iterator[StreamEvent]`. Deviation from the arch-doc's `async send(...)`
    sketch is documented in the module docstring: the contract must type the
    real seam, and synchronous was locked in during planning.
  - `DisplayRenderer` — `setup(device) / render(device, md_text) /
    append(device, md_text, index="end")`, plus a `Device` `Protocol` covering
    the `tkinter.Text` capability surface the renderer needs.
  - `WorkspaceProvider` (impl: `kbl.workspaces.WorkspaceManager`),
    `ConfigStore` (impl: `kbl.config.Config`; docstring documents the `Config()`
    no-path singleton as a deliberate implementation and that
    `active_workspace` is never persisted), `ToolCollection`,
    `FileRepository`, `ToolRegistry`.
  - Forward-declared contracts for later milestones: `EventBus` (M3),
    `Agent`/`AgentRegistry` (M4), `SubagentRegistry`/`Delegator` + frozen
    dataclasses `DelegationRequest`/`DelegationResult` (M5). Foward contracts
    carry the isolation/cancellation mandates from the roadmap in their
    docstrings.
- **`kbl/markdown_render.py`** — added `class MarkdownRenderer:` adapter
  (`setup → setup_md_tags`, `render → render_md_in_text`,
  `append → append_md`). It deliberately does **not** inherit
  `DisplayRenderer` — structural-only, so `isinstance(renderer,
  DisplayRenderer)` is a genuine protocol check, and the image-canvas backend
  in M6 can satisfy the same contract without subclassing.
- **`kbl/harness.py`** — `orchestrate` now yields `StreamEvent`s via
  `make_stream_event(...)` (same `(kind, payload)` tuples the panel drain
  already understood) and is documented + annotated as the single `Harness`
  implementation. `__call__`-based so a plain function satisfies the protocol.
- **`tests/test_contracts.py`** — handles: standalone import, no-tkinter
  import (AST walk, not substring), `make_stream_event` round-trip for every
  kind + unknown-kind rejection, `isinstance(orchestrate, Harness)` and
  `isinstance(MarkdownRenderer(), DisplayRenderer)` structural checks,
  the sync signature surface (`server/model/api_key/.../stop_event`),
  forward contracts are `Protocol`s, runtime contracts are
  `runtime_checkable`, and `DelegationRequest` is a typed frozen dataclass.
- **`tests/test_purity.py`** — added `contracts` to `PURE_SERVICES`.

## Results

- `pytest tests/` → **137 passed** in ~0.8s (125 from M1 + 12 new), headless.
- Verified: `isinstance(harness.orchestrate, contracts.Harness)` → `True`;
  `isinstance(markdown_render.MarkdownRenderer(), contracts.DisplayRenderer)` →
  `True`.
- M2 acceptance met: `contracts.py` imports cleanly standalone; both structural
  checks pass; the full suite is green.

## Notes / follow-ups

- `Harness` intentionally types the real `orchestrate` entry point rather than
  the arch-doc's `send(messages, tools, workspace, stop_event)` sketch. The
  seam contract has to describe what the seam actually is, or M6's drop-in
  swap test would be testing a fiction. `StreamEvent`s collapse to `(kind,
  payload)` pairs, so no call site needed to change.
- `EventBus`/`Agent`/`Delegator` are forward-declared now (per the arch-doc
  principle "define these first"); M3/M4/M5 flesh them out, M5's isolation
  mandates are already written into the `Delegator` docstring.
- M3 can now swap the constructor-callback + `self.master` plumbing for a
  `kbl/events.py` `EventBus` without touching the service contracts.