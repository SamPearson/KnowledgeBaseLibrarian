# M1 — Thin Chat Panel (extract LLM harness)

Status: **complete** (2026-09-23)

## Goal

Move the LLM/tool agent-loop orchestration out of `ChatPanel` into a pure
service so it can run headlessly and be reused by any frontend (the #1
architectural risk identified in `system_architecture.md`: orchestration buried
in the panel reached into `self.master` and was untestable without a GUI).

## What changed

- **New `kbl/harness.py`** (pure service, zero Tkinter):
  - `harness.orchestrate(...)` — synchronous generator over the full agent
    loop. Yields the same event tuples the panel previously queued internally:
    `("reasoning", …)`, `("content", …)`, `("tool_call", call)`,
    `("tool_result", (call, result))`, `("done", final_text)`,
    `("error", message)`. A `threading.Event stop_event` aborts the loop.
  - `harness.build_request(config, workspace)` — collects the enabled tool list
    and composes the system prompt (agent prompt + workspace instructions +
    tools + skills); accepts `tools`/`system_prompt` overrides for tests.
  - `harness.max_tool_rounds(config)` — the tool-round cap (default 8),
    extracted from the panel's private `_max_tool_rounds`.
  - Conversation ownership: tool round-trips and the final assistant reply are
    appended to the caller's `conversation` list on completion (unless stopped),
    exactly as the panel used to do — including the "Stopped after N tool
    rounds" guard.
- **`kbl/panels/chat.py`** slimmed: `_stream_worker` now just runs
  `harness.orchestrate(...)` on a worker thread, forwarding events into the
  queue. The private `_max_tool_rounds`, `_normalize_call`,
  `_assistant_tool_message`, and the inline prompt-composition/tool-loop code
  were deleted. The panel keeps everything that is genuinely view work:
  thread spawn, `root.after()` queue draining, markdown rendering, tool-call
  preview lines, message editing.
- **`tests/test_harness.py`** — headless, no network. A fake `chat_stream` is
  injected (scripted per tool-message count) and `harness.run_tool` is stubbed:
  single round, tool round-trip, loop-ends-when-no-calls, max-rounds cap, stop
  abort, error propagation, `build_request` from a real config+workspace,
  config-driven orchestrate, missing-config guard.
- **`tests/test_purity.py`** — added `harness` to `PURE_SERVICES`, so the
  no-Tkinter guard now covers the new module too.

## Results

- `pytest tests/` → **125 passed** in ~0.7s (115 from M0 + 10 new), headless.
- `kbl/panels/chat.py` imports no longer reference `context`/`toolstore`;
  `kbl.harness` is self-contained and testable in isolation.
- Behavior is preserved: same event kinds, same conversation mutation, same
  stop semantics, same round cap default and config override.

## Notes / follow-ups

- The "Stopped after N tool rounds" case previously pushed a bare string into
  the queue — a latent bug in the drain loop (it now surfaces as a
  `("done", …)`-style guard in the harness). Confirmed fixed by
  `test_max_rounds_cap`.
- M2 can now write a `Harness` contract in `contracts.py` that `orchestrate`
  satisfies: synchronous `Iterator` of typed `StreamEvent`s (the arch doc's
  `async send()` sketch was intentionally dropped — synchronous was locked in
  during planning).