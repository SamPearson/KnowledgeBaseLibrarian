# Dialogs

All dialogs are view-layer `ttk`/`tk` windows under `kbl/dialogs/` (plus the inline `WorkspaceDialog` in `main_window.py`). They share the `try: import ttkbootstrap as ttk / except ImportError: from tkinter import ttk` fallback pattern and style via `kbl.theme`. None satisfy a `~kbl.contracts` protocol; all are manually tested.

## ServerConfigDialog — `kbl/dialogs/server_config.py`
Base URL, model, and optional API key; verifies the endpoint with `chat_client.fetch_models` and surfaces `chat_client.ServerError` inline. Sets a max tool-call rounds cap that mirrors the chat panel's own cap. Published via `server_config_requested`.

## AgentManagerDialog — `kbl/dialogs/agent_manager.py`
Create, edit, rename, delete, and select agents using `kbl.agents`. On selection publishes `agent_changed` so chat switches system prompts.
Dependencies: `kbl.agents`, `kbl.theme`.

## ToolManagerDialog — `kbl/dialogs/tool_manager.py`
List, create, rename, delete, and enable/disable tools across the three `kbl.toolstore` sources. Selecting a user tool opens its `SKILL.md` (or `tools.py`) in the main editor via `file_opened`, reusing existing UI.
Dependencies: `kbl.toolstore`, `kbl.theme`.

## ThemeSelectorDialog — `kbl/dialogs/theme_selector.py`
Choose and manage themes via `kbl.themes.ThemeManager`; applies the selection app-wide.
Dependencies: `kbl.themes`, `kbl.theme`.

## ThemeEditorDialog — `kbl/dialogs/theme_editor.py`
Create and edit custom themes; `PALETTE_FIELDS` drives a field editor with `tkinter.colorchooser`. Persisted through `kbl.themes.ThemeManager`.
Dependencies: `kbl.themes`, `kbl.theme`.

## WorkspaceDialog — `kbl/main_window.py` (inline)
Directory picker shown at startup; publishes `workspace_selected`.
Dependency: `kbl.events` (`WorkspaceSelected`, `workspace_selected` topic).

## Fork implications
- Dialogs are isolated by the bus: they never touch panels directly, only publish `*_requested` topics and receive user action.
- Swapping the config/tool/agent backends (e.g. a web settings API) touches only the matching dialog + its pure module.