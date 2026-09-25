# Harness

## Purpose
The LLM/tool loop: turns a `conversation` list into an iterator of `StreamEvent`s, choosing tools, executing them, routing to sub-agents, and emitting typed events until the turn budget or a `stop_event` is exhausted. Pure service — the contract that every future backend (e.g. an image/stable-diffusion harness) must satisfy.

## Location
`kbl/harness.py` (`orchestrate`, the `Harness`-satisfying callable). The protocol lives in `kbl/contracts.py`.

## Inputs
`server, model, api_key, conversation` (positional) plus optional `workspace`, `config`, `stop_event`, `tools`, `system_prompt`, `max_rounds`, and keyword-only `agent_id`, `depth`, `delegator`, `event_sink`.

## Outputs
- `Iterator[StreamEvent]` — see `~kbl.events` for kinds (`Delegate`, `SubagentStarted/Event/Completed/Failed`, tool results, etc.).
- Side effects: tool execution, `~/.kbl` under `workspace`, delegation runs.

## Dependencies
- Pure services only: `agents`, `chat_client`, `config`, `contracts`, `delegator`, `events`, `toolstore`, `tools`. Must never import Tkinter (guarded by `tests/test_purity.py`).

## Events
- Emits the full `StreamEvent` vocabulary listed above.
- Delegation events flow through `event_sink` as `(kind, value)` tuples keyed by `task_id`.

## Contracts it satisfies
- **`Harness`**: `orchestrate` satisfies the protocol, which now (M6) carries the recursive-delegation keyword-only args so an object harness satisfies it identically.

## Subagents
Owns delegation: reserves the child's `max_turns`/`max_depth` budget, intersects tool allowlists (child's `allowed_tools` vs request `tool_allowlist`), seeds a fresh conversation (`context` + `task`, never implicit history), and passes the parent `stop_event` down so aborting the root aborts the whole tree.

## Isolation
Fully pure and synchronous; deterministic given inputs. Thread-safe by contract (no shared mutable state; `stop_event` is the only cross-thread object).

## Testability
Excellent — the arch doc's daemon-safe rule applies: `tests/test_harness.py` runs against fakes, no sockets/Tk. The `Harness` structural `isinstance` check is in `test_contracts`.

## Fork implications
- An SD-branch backend (image generation) is a new callable/object satisfying `Harness`; the UI wires it in `MainWindow._build_panels` only.
- Parallel or streaming backends must still return an `Iterator[StreamEvent]` — the UI consumes the stream, so latency hiding happens upstream.