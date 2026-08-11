"""Chat panel: placeholder for M1, wired up in M2."""

import tkinter as tk
from tkinter import ttk


class ChatPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Label(
            body, text="Chat comes in M2.", anchor="center"
        ).pack(fill="both", expand=True)

        self.input = tk.Text(self, height=3, state="disabled")
        self.input.pack(side="bottom", fill="x", padx=4, pady=4)
