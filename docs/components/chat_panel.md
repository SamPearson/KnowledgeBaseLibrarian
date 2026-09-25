# ChatPanel

## Purpose
The conversation surface: input box, agent/model selection, `HistoryView` rendering, and the worker-thread drive loop that consumes the harness's event stream.

## Location
`kbl/panels/chat.py` (`ChatPanel`).

## Inputs
- `master`, `config`, `bus`, and — after M6 — `harness: Harness | None` and `renderer: DisplayRenderer | None`.
- `server`, `model`, `api_key` from `ServerConfigDialog` (via `bus`).
- Workspace path and file-opened attachments.
- User text, agent selector, Stop button.

## Outputs
- Runs `self._harness(server, model, api_key, conversation, workspace=..., config=..., stop_event=..., event_sink=...)` on a worker thread.
- Renders assistant/tool/subagent output through `HistoryView` using the injected `renderer`.
- Publishes `user_sent` / `assistant_reply` and forwards subagent events to the bus.

## Dependencies
- `kbl.agents` (agent list/system prompt resolution), `kbl.config`, `kbl.chat_client` (`fetch_models`, `ServerError`), `kbl.events`.
- M6: `kbl.harness` (`orchestrate`) and `kbl.markdown_render` (`MarkdownRenderer`) are only the *defaults*.
- Threading via `threading.Thread` + `queue` + `root.after` (bus is UI-thread-only).

## Events
- Reads: `agent_changed`, `user_sent`, file attachments.
- Publishes: `user_sent`, `assistant_reply`, `delegation_requested`, `subagent_started/event/completed/failed` through the `event_sink` → `events` bridge.

## Contracts it satisfies
- Invokes `Harness` (`orchestrate` by default).
- Forwards a `DisplayRenderer` to `HistoryView` (`markdown_render.MarkdownRenderer` by default).

## Subagents
None of its own; delegation is upstream of the harness. It only renders subagent lifecycle events.

## Isolation
UI-thread logic is trivial; the heavy lifting (LLM loop, delegation, tool calls) is on the worker thread and in pure services. Panel keeps no domain state.

## Testability
Manual (widget). Panels are excluded from headless tests. Seams are the testable surface: any `Harness` stub can be injected and its event stream asserted without a network.

## Fork implications
- LLM swap: inject the new `Harness` at wiring time (see `main_window.md`); the drive loop is unchanged.
- Renderer swap: inject a new `DisplayRenderer`; `HistoryView` re-renders with the same event stream.