"""Image rendering for the fork's display surface (M7 fork proof #2).

The :class:`TkImageRenderer` adapter satisfies :class:`~kbl.contracts.
ImageRenderer` structurally, mirroring how :class:`kbl.markdown_render.
MarkdownRenderer` satisfies ``DisplayRenderer``: consumers depend on the
protocol, never on this class, so the fork can replace it with its real image
canvas at the wiring point.

Two surface styles are handled at runtime:

- a ``tk.Canvas``-like device (anything with ``delete``/``create_image``) gets
  the image drawn directly, scaled down to fit the canvas width;
- a ``Text``-like device falls back to a text placeholder naming the file, so
  an ``Image`` stream event never crashes a text-only renderer.

Tkinter is imported lazily (inside methods) so the module stays importable in
headless test runs, exactly like ``kbl.markdown_render``.
"""

from __future__ import annotations

from pathlib import Path

from kbl.contracts import ImageRenderer

_FALLBACK_TAG = "sd_image"


class TkImageRenderer:
    """Proof adapter for :class:`~kbl.contracts.ImageRenderer`.

    ``photo_factory`` injects the PNG→Tk photo load (default builds a
    ``tk.PhotoImage`` lazily), so ``render`` is unit-testable without a Tcl
    interpreter.
    """

    def __init__(self, photo_factory=None):
        self._photo_factory = photo_factory

    def setup(self, device) -> None:
        """No tag setup is needed for image surfaces; kept for the protocol."""

    def render(self, device, image) -> None:
        """Draw ``image`` (an ``Image`` stream event payload) onto ``device``."""
        path = Path(image)
        if not hasattr(device, "create_image"):
            device.insert("end", f"\U0001F5BC Image: {path}\n", (_FALLBACK_TAG,))
            return
        photo = self._load_photo(path)
        width = self._canvas_width(device)
        if width and photo.width() > width:
            photo = photo.subsample(
                max(1, photo.width() // width), max(1, photo.width() // width)
            )
        device.delete("all")
        device.create_image(0, 0, image=photo, anchor="nw")
        # Keep a reference so Tk doesn't garbage-collect the image.
        device._last_photo = photo

    # ---- helpers ----

    def _load_photo(self, path):
        if self._photo_factory is not None:
            return self._photo_factory(path)
        import tkinter as tk

        return tk.PhotoImage(file=str(path))

    @staticmethod
    def _canvas_width(device):
        try:
            return int(device.cget("width") or 0)
        except Exception:
            return 0