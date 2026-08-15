"""Markdown rendering for display mode.

Primary path: convert markdown to HTML and render with ``tkhtmlview``.
Fallback: style a ``tkinter.Text`` widget with tags directly.
"""

import re
import tkinter.font as tkfont

from kbl import theme

try:
    import markdown as _markdown
except ImportError:  # pragma: no cover
    _markdown = None

_INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|(?<!\*)\*[^*\n]+\*(?!\*))")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


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
    widget.tag_configure("md_hr", relief="groove", borderwidth=1)


def _tokenize_inline(text):
    tokens = []
    for part in _INLINE_RE.split(text):
        if not part:
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


def render_md_in_text(widget, md_text):
    """Render ``md_text`` into a ``Text`` widget using styled tags."""
    _setup_tags(widget)
    widget.configure(state="normal")
    widget.delete("1.0", "end")

    in_code = False
    for raw_line in (md_text or "").split("\n"):
        line = raw_line.rstrip("\r")

        if line.strip().startswith("```"):
            in_code = not in_code
            continue

        if in_code:
            widget.insert("end", line + "\n", ("md_code_block",))
            continue

        if line.strip() in ("---", "***", "___"):
            widget.insert("end", "\n", ("md_hr",))
            continue

        match = _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            widget.insert(
                "end", match.group(2).strip() + "\n", (f"md_h{level}",)
            )
            continue

        if line.lstrip().startswith(">"):
            text = line.lstrip()[1:].lstrip()
            _insert_inline(widget, text + "\n", ("md_quote",))
            continue

        _insert_inline(widget, line + "\n", None)

    widget.configure(state="disabled")


def _insert_inline(widget, text, extra_tags):
    for chunk, tag in _tokenize_inline(text):
        tags = (tag,) if tag else ()
        if extra_tags:
            tags = tags + extra_tags
        widget.insert("end", chunk, tags)
