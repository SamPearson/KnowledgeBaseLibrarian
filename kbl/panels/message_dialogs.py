"""Modal dialogs for editing and deleting messages in the chat history."""

import tkinter as tk
from tkinter import ttk


def edit_message_dialog(parent, conversation, conv_index, role, on_commit, stream_check):
    """Open a dialog to edit ``conversation[conv_index]``'s content.

    ``on_commit(new_content)`` is invoked with the edited text (caller
    persists + re-renders). ``stream_check()`` returns True when streaming.
    """
    if stream_check() or conv_index >= len(conversation):
        return
    current = conversation[conv_index].get("content") or ""

    dialog = tk.Toplevel(parent)
    dialog.title(f"Edit {role} message")
    dialog.transient(parent)
    dialog.grab_set()

    text = tk.Text(dialog, wrap="word", width=70, height=20)
    text.pack(fill="both", expand=True, padx=8, pady=8)
    text.insert("1.0", current)
    text.focus_set()
    text.tag_add("sel", "1.0", "end-1c")

    row = ttk.Frame(dialog)
    row.pack(fill="x", padx=8, pady=(0, 8))

    def _save():
        on_commit(text.get("1.0", "end-1c"))
        dialog.destroy()

    def _cancel():
        dialog.destroy()

    ttk.Button(row, text="Cancel", command=_cancel).pack(side="right", padx=(4, 0))
    ttk.Button(row, text="Save", style="Accent.TButton", command=_save).pack(side="right")
    dialog.bind("<Escape>", lambda e: _cancel())


def delete_message_dialog(parent, conversation, conv_index, on_confirm, stream_check):
    """Confirm then truncate ``conversation`` from ``conv_index`` onward."""
    if stream_check() or not (0 <= conv_index < len(conversation)):
        return

    dialog = tk.Toplevel(parent)
    dialog.title("Delete messages")
    dialog.transient(parent)
    dialog.grab_set()

    following = len(conversation) - conv_index - 1
    if following:
        detail = (
            f"Delete this message and the {following} message(s) "
            f"after it? This cannot be undone."
        )
    else:
        detail = "Delete this message? This cannot be undone."
    ttk.Label(dialog, text=detail, wraplength=320, justify="left").pack(
        padx=12, pady=12
    )

    row = ttk.Frame(dialog)
    row.pack(fill="x", padx=12, pady=(0, 12))

    def _confirm():
        on_confirm()
        dialog.destroy()

    def _cancel():
        dialog.destroy()

    ttk.Button(row, text="Cancel", command=_cancel).pack(side="right", padx=(4, 0))
    ttk.Button(row, text="Delete", style="Accent.TButton", command=_confirm).pack(side="right")
    dialog.bind("<Escape>", lambda e: _cancel())