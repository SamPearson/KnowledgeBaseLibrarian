# MainWindow

## Purpose
Application shell: owns the Tk root, lays out the three-pane workspace, and acts as the **single wiring point** where concrete services are bound into the UI. Per M6, swapping `harness.orchestrate` for `StableDiffusionHarness` (or `MarkdownRenderer` for an image renderer) happens only here.

## Location
`kbl/main_window.py` (`MainWindow`, plus the inline `WorkspaceDialog`).

## Inputs
- `workspace` CLI arg / directory chosen via `WorkspaceDialog`.
- User menu/toolbar actions (open server config, agents, tools, themes).

## Outputs
- A `ttk.Window` containing `FileTreePanel`, `EditorPanel`, and `ChatPanel` in a `ttk.Panedwindow`.
- Publishes `WorkspaceSelected` on startup and `file_opened`/`server_config_requested`/`agent_manager_requested`/`tool_manager_requested`/`theme_*` events when dialogs are requested.

## Dependencies
- `kbl.theme`, `kbl.events` (`EventBus`, `WorkspaceSelected`)
- `kbl.markdown_render` (`MarkdownRenderer`), `kbl.harness` (`orchestrate`)
- Panel classes: `panels.file_tree`, `panels.editor`, `panels.chat`
- Dialogs: `dialogs.server_config`, `dialogs.agent_manager`, `dialogs.tool_manager`, `dialogs.theme_selector`, `dialogs.theme_editor`

## Events
- Subscribes: `WorkspaceSelected` (initial workspace selection dialog).
- Publishes: `workspace_selected`, the `*_requested` dialog topics.

## Contracts it satisfies
- None directly — it is the composition root. It *wires* components that satisfy `Harness` and `DisplayRenderer` (see `~kbl.contracts`).

## Subagents
None. Delegation is triggered by chat/harness, never from the shell.

## Isolation
View-only layer; no domain logic. Can survive editing pure services without changes.

## Testability
Manual (Tk window). Pure logic it depends on is covered by daemon-safe tests. The wiring point is the one line an integration test would exercise extra-caution around.

## Fork implications
- Swapping the LLM backend: construct the new `Harness`-satisfying object here and pass it to `ChatPanel(..., harness=...)`.
- Swapping the markdown visualizer: build the new `DisplayRenderer` here once, share the single instance with both `EditorPanel(..., renderer=...)` and `ChatPanel(..., renderer=...)`.
- Panels and `main_window._build_panels` are the only two places touched — nothing under `panels/*` changes.