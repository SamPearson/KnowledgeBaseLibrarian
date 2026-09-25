# FileTreePanel

## Purpose
Mirrors a workspace directory in a `ttk.Treeview` so the user can open, create, rename, and delete files/folders from the sidebar.

## Location
`kbl/panels/file_tree.py` (`FileTreePanel`).

## Inputs
- `bus` (optional `EventBus`) to subscribe to `workspace_selected`.
- Mouse/keyboard: double-click or Enter to open, Delete to delete, right-click context menu.

## Outputs
- Publishes `FileOpened` with a `Path` when a file is opened (drives `EditorPanel` and the chat "Attached file" affordance).
- Mutates the filesystem for New File / New Folder / Delete / Refresh.
- Updates the "No workspace" label binding.

## Dependencies
- `kbl.theme` (`style_menu`), `kbl.events` (`FileOpened`, `WorkspaceSelected`)
- stdlib: `shutil`, `tkinter`, `ttkbootstrap`/`ttk` fallback.

## Events
- Subscribes: `workspace_selected` → `set_workspace(path)` + refresh.
- Publishes: `file_opened`.

## Contracts it satisfies
- None (view layer, no protocols in `~kbl.contracts`).

## Subagents
None.

## Isolation
Filesystem operations are deliberate and local; the bus abstraction means the panel never reaches into sibling panels. Panel exposes no services to pure modules.

## Testability
Manual (widget). Tree/refresh logic could be extracted later; today conftest skips Tk imports.

## Fork implications
- Replacing the sidebar with a different browser (e.g. `pygit2`-based) means reimplementing the same small event surface: consume `workspace_selected`, publish `file_opened`, call `set_workspace`.
- Mass file operations (rename policies, git integration) would land here first.