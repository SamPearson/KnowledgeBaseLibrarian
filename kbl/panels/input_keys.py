"""Editing shortcuts for the chat entry widget."""

import tkinter as tk


def bind_input_keys(inp):
    """Bind standard editing shortcuts onto a tk.Text input widget.

    Works across platforms (Tk's emacs-style Control bindings are replaced
    rather than relied upon).
    """

    def noop(event):
        return "break"

    def select_all(event):
        inp.tag_add("sel", "1.0", "end")
        return "break"

    def copy(event):
        try:
            rng = inp.tag_ranges("sel")
            if rng:
                inp.clipboard_clear()
                inp.clipboard_append(inp.get(rng[0], rng[1]))
        except tk.TclError:
            pass
        return "break"

    def cut(event):
        try:
            rng = inp.tag_ranges("sel")
            if rng:
                inp.clipboard_clear()
                inp.clipboard_append(inp.get(rng[0], rng[1]))
                inp.delete(rng[0], rng[1])
        except tk.TclError:
            pass
        return "break"

    def paste(event):
        try:
            data = inp.clipboard_get()
        except tk.TclError:
            return "break"
        if data:
            inp.insert("insert", data)
        return "break"

    def undo(event):
        try:
            inp.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def redo(event):
        try:
            inp.edit_redo()
        except tk.TclError:
            pass
        return "break"

    inp.bind("<Control-a>", select_all)
    inp.bind("<Control-A>", select_all)
    inp.bind("<Control-c>", copy)
    inp.bind("<Control-C>", copy)
    inp.bind("<Control-x>", cut)
    inp.bind("<Control-X>", cut)
    inp.bind("<Control-v>", paste)
    inp.bind("<Control-V>", paste)
    inp.bind("<Control-z>", undo)
    inp.bind("<Control-Z>", undo)
    inp.bind("<Control-y>", redo)
    inp.bind("<Control-Y>", redo)
    inp.bind("<Control-Shift-Z>", redo)
    inp.bind("<Control-Shift-z>", redo)

    # Neutralize the emacs-style Control-letter bindings Tk's Text widget
    # enables by default (Ctrl+H/K/D/T/O) which feel out of place in a
    # normal GUI editor.
    for seq in (
        "<Control-h>", "<Control-H>",
        "<Control-k>", "<Control-K>",
        "<Control-d>", "<Control-D>",
        "<Control-t>", "<Control-T>",
        "<Control-o>", "<Control-O>",
    ):
        inp.bind(seq, noop)