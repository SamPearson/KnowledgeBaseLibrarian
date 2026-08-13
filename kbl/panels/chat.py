"""Chat panel: placeholder for M1, wired up in M2."""

import tkinter as tk

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme


class ChatPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Label(
            body, text="Chat comes in M2.", anchor="center", style="Dim.TLabel"
        ).pack(fill="both", expand=True)

        self.input = tk.Text(self, height=3, state="disabled")
        theme.style_text(self.input)
        self.input.pack(side="bottom", fill="x", padx=4, pady=4)

    def _restyle(self):
        """Re-apply theme styling."""
        theme.style_text(self.input)