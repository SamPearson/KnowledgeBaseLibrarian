# EventBus

## Purpose
Typed publish/subscribe wiring (M3) that replaces `self.master` reach-in plumbing and cross-panel constructor callbacks. The bus is **UI-thread-only**: worker threads deliver via their queues, and the UI thread publishes.

## Location
`kbl/events.py` (`EventBus`, event dataclasses, topic constants).

## Inputs
- `subscribe(topic, handler)` / `unsubscribe(topic, handler)` / `publish(topic, payload)` where payload is a frozen dataclass.

## Outputs
- Fan-out of `(topic, payload)` pairs to registered handlers (UI-thread context only).

## Dependencies
- stdlib `dataclasses`, `typing`; `pathlib` for `Path` payloads. No app modules.

## Events / topics
`workspace_selected`, `file_opened`, `user_sent`, `assistant_reply`, `tool_requested`, `tool_result`, `agent_changed`, `server_config_requested`, `agent_manager_requested`, `tool_manager_requested`, `delegation_requested`, `subagent_started`, `subagent_event`, `subagent_completed`, `subagent_failed` — with matching frozen payload dataclasses (`WorkspaceSelected`, `FileOpened`, …).

## Contracts it satisfies
- None (no protocol; it *is* the transport pure services avoid — pure modules never publish on the bus; they return/emit values that the UI maps to events).

## Subagents
None. Note the naming collision: `SubagentEvent` (lifecycle payload via `event_sink`) is distinct from delegation's `SubagentEvent` — see `kbl.delegator` docstring.

## Isolation
Single-thread invariant is load-bearing: workers communicate exclusively through queues (`queue.Queue` + `root.after`), so no lock is needed on the UI thread.

## Testability
Daemon-safe unit tests (`tests/test_events.py`) cover subscribe/publish/unsubscribe and payload typing without a display.

## Fork implications
- Adding a panel/topic is additive: new topic string + frozen payload + one `subscribe`. No edits to existing handlers.
- Rich-terminal or web forks reuse the same topic vocabulary; workers still map `event_sink`/`StreamEvent` → bus topics on the UI thread.