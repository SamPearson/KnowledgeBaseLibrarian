# EditorPanel (Display mode)

## Purpose
Opens and edits workspace files. Two modes: **edit** (a plain `tk.Text`) and **display** (rendered markdown). Display mode is the fork's target for rich rendering (images, diffs) — via the M6 `renderer` seam.

## Location
`kbl/panels/editor.py` (`EditorPanel`).

## Inputs
- `master`, `config` (`ConfigStore`), and — after M6 — `renderer: DisplayRenderer | None`.
- `file_opened` events select files for editing.

## Outputs
- Renders the active file when in display mode: `self._renderer.render(self._fallback_text, content)` (writes plain text only when the renderer reports it cannot render — the fallback `tk.Text`).
- Saves edits to disk (dirty tracking + Ctrl-S), toggles edit/display.

## Dependencies
- `kbl.theme`, `kbl.markdown_render` (`MarkdownRenderer` default).
- None of the pure services (`toolstore`, `agents`, `harness`).

## Events
- Subscribes: `file_opened`. Publishes nothing.

## Contracts it satisfies
- Consumes `DisplayRenderer` (provided at construction; defaults to `MarkdownRenderer()`).

## Subagents
None.

## Isolation
Standalone. Holds no reference to the bus or chat; files are edited by path only.

## Testability
Manual (widget). The renderer seam is unit-testable: `test_contracts` already asserts `isinstance(MarkdownRenderer(), DisplayRenderer)`, so editor-level display behavior can be exercised with a fake renderer.

## Fork implications
- Swapping markdown for an image/diff renderer = pass a different `DisplayRenderer` at `MainWindow._build_panels`. No changes inside this file.
- The `_fallback_text` widget is the guaranteed-safe last resort when a renderer can't render a given file/binary.