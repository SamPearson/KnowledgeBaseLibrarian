"""Reusable ttk components that survive being squeezed.

Tk's geometry managers never refuse to over-constrain a child. When the
siblings in a row need more room than the parent can give them, ``pack``
shrinks whatever it packed last down to a 1x1 pixel allocation and that widget
is not drawn at all: no scrollbar, no ellipsis, no reflow, the button is simply
gone. ``grid`` is no kinder, it just squeezes columns instead of hiding widgets.
Neither manager will tell a parent "I am over-constrained", and no frame option
can stop it -- ``minsize`` does not exist on frames, only on a toplevel.

``ActionRow`` is a strip that makes the shortfall impossible to ignore. It knows
the natural width of everything it holds, hands any deficit to the flexible
children first (down to the floor declared for each), and reports the width it
really needs through ``on_min_width`` so the window can refuse to get narrower.
Use it for every row that holds buttons.
"""

import tkinter as tk
import tkinter.font as tkfont

from kbl import theme

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

# Widgets whose -width option counts characters. A tk.Frame -width counts
# pixels, so the class has to be checked rather than the option read blindly.
_CHAR_WIDTH_WIDGETS = (
    ttk.Combobox,
    ttk.Entry,
    ttk.Spinbox,
    ttk.Button,
    tk.Text,
    tk.Entry,
    tk.Spinbox,
)

_FONT_CACHE = {}


def _style_name(widget):
    try:
        name = widget.cget("style")
    except tk.TclError:
        name = ""
    return name or widget.winfo_class()


def _char_advance(widget):
    """Pixel width of one character in a widget's effective ttk font."""
    name = _style_name(widget)
    try:
        spec = theme.current_style().lookup(name, "font")
    except tk.TclError:
        spec = None
    key = (name, str(spec))
    advance = _FONT_CACHE.get(key)
    if advance is None:
        try:
            font = tkfont.Font(root=widget, font=spec)
        except tk.TclError:
            font = tkfont.nametofont("TkDefaultFont", root=widget)
        advance = max(1, font.measure("0"))
        _FONT_CACHE[key] = advance
    return advance


def _width_chars(widget):
    """The widget's -width option in characters, or None if it is not a
    char-sized widget."""
    if not isinstance(widget, _CHAR_WIDTH_WIDGETS):
        return None
    try:
        return int(widget.cget("width"))
    except (tk.TclError, ValueError):
        return None


def _padx_width(pack_kw):
    padx = pack_kw.get("padx", 0)
    if isinstance(padx, (tuple, list)):
        return sum(padx)
    return padx


def elide_middle(text, limit=48, marker="..."):
    """Shorten `text` around its middle, keeping both ends readable.

    Labels packed next to buttons have to be short. A ttk.Label cannot shrink
    (its -width is a wrap hint, not a size limit), so an unbounded path in a
    status or title label silently pushes the buttons beside it out of the
    strip. Eliding the text at the point it is displayed keeps the full value
    in config untouched while the row stays a predictable size.
    """
    text = str(text)
    if limit <= 0 or len(text) <= limit:
        return text
    keep = limit - len(marker)
    head = (keep + 1) // 2
    tail = keep - head
    return f"{text[:head]}{marker}{text[len(text) - tail:]}" if tail else f"{text[:head]}{marker}"


def _distribute(amount, weights):
    """Split `amount` across `weights`, the biggest share to the biggest weight.

    Largest-remainder rounding, so the parts always add up to `amount` exactly.
    Without it the reported minimum drifts by a pixel per row per refit.
    """
    total = sum(weights)
    if amount <= 0 or total <= 0:
        return [0] * len(weights)
    exact = [amount * w / total for w in weights]
    parts = [int(part) for part in exact]
    order = sorted(
        range(len(weights)),
        key=lambda i: exact[i] - parts[i],
        reverse=True,
    )
    for index in order[: amount - sum(parts)]:
        parts[index] += 1
    return parts


class _Metrics:
    """Pixel geometry of one ttk style, learned from a live widget.

    A char-sized widget requests exactly ``chars * advance + overhead``. The
    per-character advance falls out of the font, but the overhead is chrome
    (padding, arrow, border) that varies per style and per theme, so it can
    only be measured.
    """

    __slots__ = ("advance", "overhead")

    def __init__(self, advance, overhead):
        self.advance = advance
        self.overhead = overhead

    def width(self, chars):
        return chars * self.advance + self.overhead

    def chars_for(self, px, natural, floor):
        if px <= self.width(floor):
            return floor
        chars = int(round((px - self.overhead) / self.advance))
        return max(floor, min(natural, chars))


class _Slot:
    """One child of an ActionRow, with the width bookkeeping for it."""

    __slots__ = ("widget", "padx", "chars", "floor_chars", "metrics", "applied")

    def __init__(self, widget, padx, chars, floor_chars):
        self.widget = widget
        self.padx = padx
        self.chars = chars
        self.floor_chars = floor_chars
        self.metrics = None
        self.applied = None

    @property
    def flexible(self):
        return self.floor_chars is not None

    def natural_px(self):
        if not self.flexible:
            return self.widget.winfo_reqwidth() + self.padx
        return self.metrics.width(self.chars) + self.padx

    def floor_px(self):
        if not self.flexible:
            return self.natural_px()
        return self.metrics.width(self.floor_chars) + self.padx

    def apply_px(self, px):
        if not self.flexible or self.metrics is None:
            return
        chars = self.metrics.chars_for(px, self.chars, self.floor_chars)
        if chars == self.applied:
            return
        self.applied = chars
        self.widget.configure(width=chars)


class ActionRow(ttk.Frame):
    """A horizontal strip that keeps its buttons on screen at any width.

    Children added with ``flex_chars=N`` give up width first, never below N
    characters. Every other child keeps its natural width, so actions stay
    visible when the pane is dragged narrow. When the whole row still does not
    fit, the leftover is reported to ``on_min_width`` -- that is the width a
    window must not go below.
    """

    def __init__(self, master=None, on_min_width=None, **kwargs):
        super().__init__(master, **kwargs)
        self._on_min_width = None
        self._slots = []
        self._metrics = {}
        self._min_width = 0
        self.bind("<Configure>", self._on_configure, add="+")
        if on_min_width is not None:
            self.on_min_width = on_min_width

    @property
    def on_min_width(self):
        """Callback invoked with the row's required width whenever it changes."""
        return self._on_min_width

    @on_min_width.setter
    def on_min_width(self, callback):
        self._on_min_width = callback
        if callback is not None:
            callback(self._min_width)

    # ---- construction ----

    def add(self, widget, side="left", flex_chars=None, **pack_kw):
        """Pack `widget` into the row and start tracking its width.

        `flex_chars` is the floor, in characters, that this widget may shrink
        to. Leave it off for anything that must keep its full width, which is
        every button: an action that is merely narrow is still usable, an
        action that is invisible is not.
        """
        chars = None
        floor = None
        if flex_chars is not None:
            chars = _width_chars(widget)
            if chars is None:
                raise ValueError(
                    f"{type(widget).__name__} has no character-based -width "
                    "option, so it cannot be given a flex_chars floor"
                )
            floor = max(1, min(flex_chars, chars))
        self._slots.append(_Slot(widget, _padx_width(pack_kw), chars, floor))
        widget.pack(side=side, **pack_kw)
        return widget

    # ---- fitting ----

    @property
    def min_width(self):
        """Width the row needs with every child at its floor, in pixels."""
        return self._min_width

    def fit(self, available=None):
        """Refit the row into `available` pixels (defaults to its real width)."""
        if available is None:
            available = self.winfo_width()
        if not self._slots:
            return
        self._resolve_metrics()
        natural = [slot.natural_px() for slot in self._slots]
        needed = sum(natural)
        if available <= 1:
            # Not laid out yet (never mapped, or clipped to nothing by a parent
            # that is itself too small). Nothing can be applied, but the row
            # still knows what it needs, and a caller enforcing a minimum has
            # to be told the real number rather than a misleading zero.
            self._publish(needed)
            return
        if available >= needed:
            for slot, width in zip(self._slots, natural):
                slot.apply_px(width)
            self._publish(needed)
            return
        slack = [
            max(0, width - slot.floor_px())
            for slot, width in zip(self._slots, natural)
        ]
        spare = sum(slack)
        if spare <= 0:
            self._publish(needed)
            return
        for slot, width, shave in zip(self._slots, natural, _distribute(needed - available, slack)):
            slot.apply_px(width - shave)
        self._publish(needed - min(needed - available, spare))

    def remeasure(self):
        """Drop the cached font metrics and refit, after a theme change."""
        self._metrics.clear()
        for slot in self._slots:
            slot.metrics = None
            slot.applied = None
        self.fit()

    def _on_configure(self, event):
        if event.widget is not self:
            return
        self.fit(event.width)

    def _resolve_metrics(self):
        """Learn the pixel geometry of each shrinkable child.

        A child is put back to its authored width before being measured, and
        the font advance is re-checked every pass, so a theme change rebuilds
        the numbers without anyone having to remember to call remeasure().
        """
        for slot in self._slots:
            if not slot.flexible:
                continue
            key = _style_name(slot.widget)
            advance = _char_advance(slot.widget)
            known = self._metrics.get(key)
            if known is not None and known.advance == advance:
                slot.metrics = known
                continue
            if _width_chars(slot.widget) != slot.chars:
                slot.widget.configure(width=slot.chars)
            slot.widget.update_idletasks()
            measured = _Metrics(
                advance,
                max(0, slot.widget.winfo_reqwidth() - slot.chars * advance),
            )
            self._metrics[key] = measured
            slot.metrics = measured

    def _publish(self, width):
        width = int(round(width))
        if width == self._min_width:
            return
        self._min_width = width
        if self._on_min_width is not None:
            self._on_min_width(width)
