# markdown_render

## Purpose
Renders markdown onto a `tkinter.Text` widget by styling it directly with theme tags (headings, code, links, bold) rather than via an off-screen HTML widget. M6 removed the dead `tkhtmlview`/`md_to_html` path and made `MarkdownRenderer` the `DisplayRenderer` implementation that does the tag work.

## Location
`kbl/markdown_render.py` (`MarkdownRenderer`, module-level tag helpers).

## Inputs
- `setup(widget)` — configure the theme tags on a target `tk.Text`.
- `render(widget, md_text)` / `append(widget, md_text, index='end')` — insert converted text.

## Outputs
Styled text operations on the given widget; returns nothing.

## Dependencies
- `kbl.theme` (palette-driven tag colors), `kbl.contracts` (`DisplayRenderer`).

## Events
None.

## Contracts it satisfies
- **`DisplayRenderer`** (`setup`/`render`/`append`), verified structurally in `tests/test_contracts.py`.

## Subagents
None.

## Isolation
Pure-ish: no Tk instance is created (widgets tinted are passed in), so it can be tested headlessly and reused by any panel that shows user content.

## Testability
Strong. `MarkdownRenderer` against a mock/fake `Text` widget asserts protocol membership; app-level daemon-safe tests keep it importable.

## Fork implications
- An image/token renderer (e.g. `ImageRenderer`) implements the same protocol and is swapped in at `MainWindow._build_panels`. Consumers (`EditorPanel`, `HistoryView`) call only through the injected `DisplayRenderer`.
- Removed M6 code — `md_to_html`/`_style_html`/the optional `import markdown` — can be resurrected on a branch that reintroduces `tkhtmlview`.