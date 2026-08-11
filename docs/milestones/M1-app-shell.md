# M1 — App Shell

## Goal

A working window with the core editor surfaces, no AI. Everything here is
standard tkinter plus one small library for markdown display. This milestone
is big in surface area but small in risk.

## Components

- Window + panel layout
- File tree
- Editor (edit mode)
- Display mode (rendered markdown)
- Workspaces
- Config persistence

## Panel layout

- `ttk.PanedWindow` for splitters. Python has no free-form docking; we use a
  fixed set of layout presets instead, with sizes adjusted by dragging splitters.
- Panels: file tree, editor, preview, chat (placeholder until M2).
- Presets, e.g.: tree+editor / editor+preview / tree+editor+preview /
  tree+editor+chat / all four.
- Panel sizes and current preset saved to config.

### Deferred

- Free-form drag-to-dock.

## Workspaces

- A user-managed list of workspace paths (top-level folders) plus one active
  workspace, stored in config.
- Managed via the Workspace menu and a Workspaces dialog (add / remove /
  activate). Switching activates a new workspace and repopulates the tree.
- The file tree mirrors the active workspace (see below).

## File tree

- `ttk.Treeview`, backed by a real workspace directory on disk. Shows folders
  and `.md` files recursively.
- Add file = new `.md` file in the selected folder. Add folder = new subfolder
  (nested). Delete works on both files and folders (recursive, confirmed).
- Only `.md` files open in the editor.

### Why back it to disk

The wiki *is* a directory. Mirroring it on disk now sets up M3, where the model
reads those same files for context.

## Editor

- `tkinter.Text` widget for editing. Edit mode is editable; display mode is a
  read-only rendered view of the same text.
- Markdown display: `markdown` (or `markdown2`) to HTML + `tkhtmlview`
  (`HTMLLabel`) to render. Supports a useful HTML subset; good enough for a wiki.
- Fallback if `tkhtmlview` misbehaves: hand-rolled display mode that styles
  `Text` tags (headers, bold, code) directly.
- Dirty tracking; Ctrl+S saves.

### Deferred

- Live preview while typing (display mode renders once on switch for now).

## Config

- JSON config file in the user config dir: layout preset, panel sizes,
  workspace path. Grows to hold model config in M2 and plugin settings in M4.

## Acceptance criteria

- Launch opens a window with a default layout.
- Add and remove `.md` files and folders in the tree; tree reflects the
  directory on disk.
- Open a file, edit, save, reopen to confirm it persisted.
- Toggle edit/display; display renders headers, lists, and code blocks.
- Panel sizes and layout survive restart.
- Add, remove, and switch workspaces; the tree follows the active workspace.
