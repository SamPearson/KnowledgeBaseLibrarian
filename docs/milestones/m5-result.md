# M5 — Delegation orchestrator (model-driven `delegate(...)`)

Status: **complete** (2026-09-23)

## Goal

Let a `can_delegate_to` agent issue a `delegate(agent_id, task, context)` tool
call that spins up one sub-agent run: isolated scope (own conversation),
per-agent tool allowlist, depth and turn caps, and a lifecycle correlated by a
single `task_id` — all surfaced through the existing `EventBus` so the GUI
never needs to know a delegation happened under the hood.

## What changed

- **`kbl/delegator.py`** (new, 272 lines, pure service — no Tkinter import):
  - `SubagentDelegator` — the M5 standing implementation of the `Delegator`
    contract. `delegate(request, stop_event=None, depth=0)`:
    - validates the caller exists, the child exists, the child is in the
      caller's cascade-sure `can_delegate_to`, `depth` is under the child's
      `max_depth`, and the child's `max_turns` still fits the remaining
      delegated-turn budget;
    - builds a **fresh** conversation: only the request's explicit `context`
      messages plus the delegated `task` as the final user message — never
      implicit parent history;
    - hands control to a `run_agent` callable (the harness's recursive
      orchestrator) with the child's own tool list (its `allowed_tools`,
      intersected by the request's `tool_allowlist`), `max_rounds` = the
      child's `max_turns`, and the same `stop_event`, so aborting the parent
      cancels the whole tree;
    - relays every child stream event to the `event_sink` as `SubagentEvent`,
      and emits `DelegationRequested` → `SubagentStarted` → `SubagentCompleted`
      (or `SubagentFailed`) — all carrying the same `task_id`;
    - returns a `DelegationResult(task_id, result, tool_calls)`; on any
      failure (bad args, caps, missing runner, child error event, raised
      exception) it returns a graceful failure string so the parent LLM gets
      a normal tool result.
  - `invoke_delegate(delegator, call, caller_id, stop_event=None, depth=0)` —
    parses the `delegate` tool arguments (error-bearing on malformed JSON,
    non-object args, or missing `agent_id`/`task`) and turns them into a
    `DelegationRequest`.
  - `make_delegate_tool()` — builds the `delegate` tool schema. The harness
    intercepts `delegate` calls before `run_tool`; the placeholder `func`
    only fires if executed outside a harness loop (it explains itself).
  - `max_delegated_turns(config, default=32)` — the total delegated-turn
    budget for one root run, read from `config.max_delegated_turns` with the
    same fallback discipline as `harness.max_tool_rounds`.
- **`kbl/harness.py`**:
  - `build_request(config, workspace=None, agent_id=None)` — `agent_id`
    selects whose allowlist/delegation settings apply; when the selected
    agent has a non-empty `can_delegate_to`, the `delegate` tool is appended
    to its tool list, so the tool can only ever appear for an agent that
    explicitly opted in.
  - `orchestrate(...)` gains keyword-only `agent_id`, `depth`, `delegator`,
    and `event_sink`. A `delegate` tool call is intercepted (not run as a
    plain tool) and routed through the delegator; the delegator's `run_agent`
    is `orchestrate` itself recursing with the child's scoped conversation,
    its own tool allowlist, and `depth + 1`.
- **`kbl/config.py`** — default `"max_delegated_turns": 32`.
- **`kbl/events.py`** — the five delegation payloads (`DelegationRequested`,
  `SubagentStarted`, `SubagentEvent`, `SubagentCompleted`, `SubagentFailed`)
  were forward-declared in M3; **unchanged** here. `topic_for(payload)` maps
  each to `delegation_requested` / `subagent_started` / `subagent_event` /
  `subagent_completed` / `subagent_failed`.
- **`kbl/panels/chat.py`** — the stream worker passes an `event_sink` into
  `orchestrate`; sub-agent topic payloads arriving on the request queue are
  relayed onto the bus (`bus.emit(payload)`). No delegation logic in the
  panel.
- **`kbl/panels/history_view.py`** — five render methods
  (`render_delegation_requested`, `render_subagent_started`,
  `render_subagent_event`, `render_subagent_completed`,
  `render_subagent_failed`) plus a `subagent` text tag. The chat history
  shows the sub-agent lifecycle inline (`▸ delegate → agent: task`, `✳
  started <task_id>`, streamed child content, `✓ <preview>` / `✗ failed`).
- **`kbl/main_window.py`** — subscribes the mediator to all five sub-agent
  topics and forwards payloads to the chat panel's history view (render-only;
  the bus already exists — this milestone simply wires the new topics
  through it).

## Design notes

- **Isolation is strict.** A child sees only (a) its own `context` + `task`
  and (b) its own tool allowlist. The parent's allowlist never has to be
  checked against the child's — the child runs with the child's list, further
  narrowed only by the request's `tool_allowlist`.
- **Acyclic dependency.** `harness → delegator`, never the reverse. The
  delegator receives `run_agent` at construction, so `kbl/harness.py` can
  import `kbl/delegator.py` without a cycle.
- **Cleaner than a queue on a worker thread.** The delegation lifecycle stays
  synchronous: the same `Iterator[StreamEvent]` that drives the parent also
  drives the child (recursively). Panel mutation stays on the UI thread via
  the existing request queue; the bus only ever receives on the UI thread.
- **`subagent_event` never re-lists the `done` event** — `SubagentCompleted`
  already carries the result, so the terminal stream event is filtered out of
  the relay to avoid double-reporting.

## Results

- `pytest tests/test_delegator.py` → **16 passed** (new; parsing, schema,
  happy path, tool-call passthrough, every failure branch, budget
  accumulate-across-children, budget underflow/overflow, unknown caller /
  unknown child / not-delegable / depth-cap / no-runner / child-error /
  child-exception).
- `pytest tests/test_harness.py` → **18 passed** (4 new: delegate tool added
  for a `can_delegate_to` agent, omitted for the default agent, coexist with
  an allowlist, and full orchestrate→delegate→subagent end-to-end via bus
  sink correlation).
- `pytest tests/test_contracts.py` → **14 passed** (delegation result +
  delegator-protocol checks).
- `pytest tests/test_purity.py` → **1 passed** (`delegator` added to
  `PURE_SERVICES`; AST guard confirms no Tkinter import).
- Full suite: `pytest tests/` → **190 passed**, headless.

## M5 acceptance

- A D&D-style scenario (parent + 1 child) works end-to-end:
  `can_delegate_to` parent → `delegate(agent_id, task)` tool call → child
  runs on its own conversation → parent receives exactly the child's result
  text → `task_id` correlates `SubagentStarted`/`SubagentEvent`/
  `SubagentCompleted`.
- Parent's tool allowlist grants the child nothing the child's own allowlist
  forbids — the child runs on its own tool list, optionally narrowed by the
  request's `tool_allowlist`.
- M0 green: full suite passes with zero Tkinter imports in pure services.

## Notes / follow-ups

- `max_depth` is enforced as a *check* on entry (a child at depth ≥ its
  `max_depth` refuses to go deeper); the roadmap's "single-level first" is
  satisfied because the default `max_depth = 1` forbids grandchild delegation.
- Child failure messages are plain strings returned to the parent as a normal
  tool result; a full structured error schema would be a future nicety.
- The UI is render-only for sub-agent events. A follow-up could add a
  dedicated sub-agent panel or collapsible tree once a second real use case
  (D&D) lands.