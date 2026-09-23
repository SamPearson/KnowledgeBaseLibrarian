# M3 — EventBus + mediator MainWindow

Status: **complete** (2026-09-23)

## Goal

Replace the `self.master` reach-in plumbing and cross-panel constructor
callbacks with a typed event bus (`kbl/events.py`), and turn `MainWindow`
into a mediator that routes events to panels instead of passing factory
callbacks through panel constructors.

## What changed

- **New `kbl/events.py`** (pure service, stdlib only, zero Tkinter):
  - `EventBus` — synchronous, in-process publish/subscribe (`subscribe`,
    `unsubscribe`, `publish`, `emit`). Satisfies `contracts.EventBus`; the
    bus is UI-thread only — worker threads hand events to the UI thread via
    their queues and the UI thread publishes. `emit` resolves the topic from
    a class registry (`_TOPIC_BY_CLASS`) and raises `ValueError` for
    unregistered payload types.
  - Typed, frozen payload dataclasses:
    `WorkspaceSelected(workspace)`, `FileOpened(path)`,
    `UserSent(message, attachments=())`, `AssistantReply(message)`,
    `ToolRequested(name, args)`, `ToolResult(name, result, error=None)`,
    `AgentChanged(agent_id)`, `ServerConfigRequested()`,
    `AgentManagerRequested()`, `ToolManagerRequested()`,
    `DelegationRequested(caller_id, agent_id, task, context, tool_allowlist)`,
    plus the four `Subagent*` events. `topic_for(type)` maps class → topic.
- **`kbl/main_window.py`** — mediator rewrite:
  - `MainWindow.__init__` now owns an `EventBus` and passes it to
    `FileTreePanel(bus=...)` and `ChatPanel(bus=...)`; the
    `on_open`/`on_configure_server`/`on_manage_agents` constructor callbacks
    are gone.
  - Mediator subscription: `file_opened → editor.open`,
    `server_config_requested → _show_server_config`,
    `agent_manager_requested → _show_agent_manager`.
  - `_activate_workspace` emits `WorkspaceSelected` instead of calling
    `tree.set_workspace` / `chat._on_workspace_changed` directly; startup
    emits `WorkspaceSelected` for the persisted active workspace.
- **`kbl/panels/chat.py`** — slimmed from 878 → 588 lines:
  - `_manage_agents`/`_configure_server`/missing-config `_send` emit
    `AgentManagerRequested()` / `ServerConfigRequested()` instead of walking
    `self.master`.
  - All rendering moved into the new **`kbl/panels/history_view.py`**
    (`HistoryView(master, on_edit, on_delete, stop_progress)`) in this
    milestone step: streaming append/thinking/collapse/toggle, message
    dividers, edit-footers, and `render_history`/`render_assistant`/
    `render_tool_call`/`render_tool_result`. Chat keeps the orchestration:
    conversation store, `_send`/attachments, the `harness.orchestrate`
    stream worker + queue drain, and stop/finish.
- **`kbl/panels/file_tree.py`** — `_open_selected` and `new_file` emit
  `FileOpened`; subscribes `workspace_selected → set_workspace`. The
  `util/open .md` fallback stub remains for M6 (delegate to `editor.open`).
- **`tests/test_events.py`** (new, 17 tests) — standalone import, no-tkinter
  AST check, contract-conformance surface (`subscribe`/`unsubscribe`/
  `publish`), subscription order, unsubscribe semantics, `emit` topic
  resolution + `ValueError` on unregistered classes, frozen payload
  typo-safety, `topic_for`, and payload default values.
- **`tests/test_purity.py`** — added `events` to `PURE_SERVICES`.

## Results

- `pytest tests/` → **154 passed** (137 from M2 + 17 new) headless.
- M3 acceptance greps:
  - `self.master.` in `kbl/panels/` → **0 hits**.
  - `kbl/panels/chat.py` → **588 lines** (< 800).
  - Full suite green.

## Notes / follow-ups

- `history_view.py` houses the render state previously scattered in chat.py
  (`_message_blocks`, `_thinking_*`, `_thought_blocks`, `_dividers`, ...),
  so an M6 display-seam swap can touch one module instead of a third of the
  chat panel.
- `main_window.py` still calls `chat.persist()` directly on workspace switch
  and close — that is a mediator calling a panel lifecycle method, not
  panel-to-panel coupling, so it stays explicit.
- Forward contracts for `Agent*`/`Delegator`/`Subagent*` events already exist
  in `contracts.py`; M4 (agents) and M5 (subagents/delegation) can now publish
  to the bus with no wiring changes.