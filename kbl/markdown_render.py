"""Markdown rendering for display mode.

Primary path: convert markdown to HTML and render with ``tkhtmlview``.
Fallback: style a ``tkinter.Text`` widget with tags directly.
"""

import re
import tkinter.font as tkfont
import unicodedata

from kbl import theme
from kbl.contracts import DisplayRenderer

try:
    import markdown as _markdown
except ImportError:  # pragma: no cover
    _markdown = None

_INLINE_RE = re.compile(
    r"(\[[^\]]+\]\([^)]+\)|\*\*.+?\*\*|`[^`]+`|(?<!\*)\*[^*\n]+\*(?!\*))"
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def md_to_html(text):
    """Convert markdown to HTML with theme colors applied inline.

    tkhtmlview's parser ignores the widget's foreground and does not
    support ``<style>`` blocks, so the theme palette is baked into the
    markup as inline styles.
    """
    if _markdown is None:
        return None
    html = _markdown.markdown(
        text or "",
        extensions=["fenced_code", "tables", "sane_lists"],
    )
    return _style_html(html)


def _style_html(html):
    p = theme.PALETTE
    html = f'<div style="color: {p["ink"]}">{html}</div>'
    accent = f'style="color: {p["accent"]}" '
    code = (
        f'style="background-color: {p["slate_alt"]}; '
        f'color: {p["chrome_text"]}"'
    )
    html = re.sub(r"<h([1-6])>", rf"<h\1 {accent}>", html)
    html = re.sub("<a href=", f"<a {accent}href=", html)
    html = re.sub("<pre>", f"<pre {code}>", html)
    html = re.sub("<code>", f"<code {code}>", html)
    return html


def _disp_width(text):
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _setup_tags(widget):
    base = tkfont.Font(font=widget.cget("font"))
    family = base.actual("family")
    size = base.actual("size")
    monospace = theme.MONO_FAMILY

    for level in range(1, 7):
        widget.tag_configure(
            f"md_h{level}",
            font=(family, size + (7 - level), "bold"),
            spacing1=6,
            spacing3=4,
        )
    widget.tag_configure("md_bold", font=(family, size, "bold"))
    widget.tag_configure("md_italic", font=(family, size, "italic"))
    widget.tag_configure("md_strike", overstrike=True)
    widget.tag_configure(
        "md_code_inline",
        font=(monospace, size, "normal"),
        background=theme.PALETTE["parchment_alt"],
    )
    widget.tag_configure(
        "md_code_block",
        font=(monospace, size, "normal"),
        background=theme.PALETTE["parchment_alt"],
        spacing1=2,
        spacing3=2,
    )
    widget.tag_configure(
        "md_quote",
        foreground=theme.PALETTE["ink_soft"],
        lmargin1=16,
        lmargin2=16,
    )
    widget.tag_configure("md_hr", foreground=theme.PALETTE["accent"])
    widget.tag_configure(
        "md_link", foreground=theme.PALETTE["accent"], underline=True
    )
    widget.tag_configure("md_mono", font=(monospace, size, "normal"))
    widget.tag_configure(
        "md_table_cell",
        background=theme.PALETTE["parchment_alt"],
    )
    widget.tag_configure(
        "md_table_header",
        foreground=theme.PALETTE["accent"],
        background=theme.PALETTE["slate_alt"],
        font=(monospace, size, "bold"),
    )


def _tokenize_inline(text):
    tokens = []
    for part in _INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("[") and "](" in part:
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            if m:
                tokens.append((m.group(1), "md_link"))
                continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            tokens.append((part[2:-2], "md_bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            tokens.append((part[1:-1], "md_code_inline"))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            tokens.append((part[1:-1], "md_italic"))
        else:
            tokens.append((part, None))
    return tokens


def _insert_inline(widget, text, extra_tags, index="end"):
    for chunk, tag in _tokenize_inline(text):
        tags = (tag,) if tag else ()
        if extra_tags:
            tags = tags + extra_tags
        widget.insert(index, chunk, tags)


def _is_table_sep(line):
    s = line.strip()
    if "|" not in s:
        return False
    inner = s.replace("|", "").replace(" ", "")
    if not inner:
        return False
    return "-" in inner and all(c in "-:" for c in inner)


def _split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _parse_align(sep_cells):
    aligns = []
    for c in sep_cells:
        c = c.strip()
        left = c.startswith(":")
        right = c.endswith(":")
        if left and right:
            aligns.append("center")
        elif right:
            aligns.append("right")
        else:
            aligns.append("left")
    return aligns


def _cell_disp_width(raw):
    return sum(_disp_width(t) for t, _ in _tokenize_inline(raw))


def _norm_row(cells, ncol):
    if len(cells) < ncol:
        return cells + [""] * (ncol - len(cells))
    return cells[:ncol]


def _render_table(widget, header, sep, data, index="end"):
    sep_cells = _split_row(sep)
    aligns = _parse_align(sep_cells)
    header_cells = _split_row(header)
    data_cells = [_split_row(d) for d in data]
    ncol = max(len(header_cells), len(sep_cells))
    ncol = max(ncol, *(len(r) for r in data_cells), 1)
    header_cells = _norm_row(header_cells, ncol)
    data_cells = [_norm_row(r, ncol) for r in data_cells]
    if len(aligns) < ncol:
        aligns = aligns + ["left"] * (ncol - len(aligns))

    widths = [0] * ncol
    for col in range(ncol):
        w = _cell_disp_width(header_cells[col])
        for row in data_cells:
            w = max(w, _cell_disp_width(row[col]))
        widths[col] = w

    def hseg(left, mid, right):
        return left + mid.join("─" * (w + 2) for w in widths) + right

    widget.insert(index, "\n", ())
    widget.insert(index, hseg("┌", "┬", "┐") + "\n", ("md_mono",))
    _insert_table_row(widget, header_cells, widths, aligns, True, index=index)
    widget.insert(index, hseg("├", "┼", "┤") + "\n", ("md_mono",))
    for row in data_cells:
        _insert_table_row(widget, row, widths, aligns, False, index=index)
    widget.insert(index, hseg("└", "┴", "┘") + "\n", ("md_mono",))
    widget.insert(index, "\n", ())


def _insert_table_row(widget, cells, widths, aligns, is_header, index="end"):
    widget.insert(index, "│", ("md_mono",))
    for col in range(len(cells)):
        raw = cells[col]
        segs = _tokenize_inline(raw)
        disp = sum(_disp_width(t) for t, _ in segs)
        gap = max(0, widths[col] - disp)
        if aligns[col] == "center":
            l_space, r_space = divmod(gap, 2)
        elif aligns[col] == "right":
            l_space, r_space = gap, 0
        else:
            l_space, r_space = 0, gap
        cell_tags = ("md_mono", "md_table_cell")
        if is_header:
            cell_tags = cell_tags + ("md_table_header",)
        widget.insert(index, " ", cell_tags)
        if l_space:
            widget.insert(index, " " * l_space, cell_tags)
        for text, tag in segs:
            # Keep only color-based tags (link) inside cells so monospace
            # alignment is preserved; drop font-changing emphasis.
            seg_tag = tag if tag == "md_link" else None
            t = (seg_tag,) if seg_tag else ()
            widget.insert(index, text, cell_tags + t)
        if r_space:
            widget.insert(index, " " * r_space, cell_tags)
        widget.insert(index, " ", cell_tags)
        widget.insert(index, "│", ("md_mono",))
    widget.insert(index, "\n", ("md_mono",))


def render_md_in_text(widget, md_text):
    """Render ``md_text`` into a ``Text`` widget using styled tags."""
    _setup_tags(widget)
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    _render_body(widget, md_text or "")
    widget.configure(state="disabled")


def append_md(widget, md_text, index="end"):
    """Append markdown rendering at ``index`` (default ``"end"``) of ``widget``
    without clearing it or altering its ``state``. The md tags must already be
    configured via :func:`setup_md_tags`."""
    _render_body(widget, md_text or "", index)


def setup_md_tags(widget):
    """Configure the markdown display tags on ``widget`` (idempotent)."""
    _setup_tags(widget)


class MarkdownRenderer:
    """Adapter so the module-level render helpers satisfy DisplayRenderer.

    Intentionally does *not* inherit from the Protocol: satisfaction is
    structural, verified by ``isinstance(renderer, DisplayRenderer)`` at
    runtime. Any component that needs markdown rendering depends on the
    :class:`DisplayRenderer` contract instead of this class, so the renderer
    can be swapped (roadmap M6 fork-proofing) without touching the consumer.
    """

    def setup(self, device):
        setup_md_tags(device)

    def render(self, device, md_text):
        render_md_in_text(device, md_text)

    def append(self, device, md_text, index="end"):
        append_md(device, md_text, index)


def _render_body(widget, md_text, index="end"):
    lines = (md_text or "").replace("\r\n", "\n").split("\n")
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                widget.insert(index, lines[i] + "\n", ("md_code_block",))
                i += 1
            i += 1
            continue

        if stripped == "":
            i += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            widget.insert(
                "end", heading.group(2).strip() + "\n", (f"md_h{level}",)
            )
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            widget.insert(index, "─" * 30 + "\n", ("md_hr",))
            i += 1
            continue

        if stripped.startswith(">"):
            widget.insert(
                "end", stripped.lstrip(">").strip() + "\n", ("md_quote",)
            )
            i += 1
            continue

        if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = lines[i]
            sep = lines[i + 1]
            j = i + 2
            data = []
            while j < n and "|" in lines[j].strip() and lines[j].strip() != "":
                data.append(lines[j])
                j += 1
            _render_table(widget, header, sep, data, index=index)
            i = j
            continue

        list_match = _LIST_RE.match(line)
        if list_match:
            indent = len(list_match.group(1))
            marker = list_match.group(2)
            content = list_match.group(3)
            level = indent // 2
            bullet = "•" if marker in ("-", "*", "+") else f"{marker} "
            widget.insert(index, "  " * level + bullet + " ")
            _insert_inline(widget, content + "\n", None, index=index)
            i += 1
            continue

        _insert_inline(widget, line + "\n", None, index=index)
        i += 1
