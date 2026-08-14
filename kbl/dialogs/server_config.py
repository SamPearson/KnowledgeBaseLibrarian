"""Server configuration dialog: base URL, model, and optional API key."""

import tkinter as tk
from tkinter import messagebox

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme
from kbl.chat_client import ServerError, fetch_models


class ServerConfigDialog(tk.Toplevel):
    """Configure the OpenAI-compatible server and model.

    The user enters a single server URL covering protocol/host/port and any
    path suffix (e.g. ``http://localhost:11434/v1`` for Ollama or
    ``http://localhost:8080/v1`` for llama.cpp), an optional API key, and a
    model name. The model list can be fetched from the server's ``/v1/models``
    endpoint for a dropdown, but manual entry is always allowed.
    """

    def __init__(self, master, on_saved):
        super().__init__(master)
        self.on_saved = on_saved

        self.title("Server Configuration")
        self.geometry("560x260")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        self._build()

        self._focus_entry.focus_set()

    def _build(self):
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        server = ttk.LabelFrame(frame, text="Server URL", padding=8)
        server.pack(fill="x", pady=(0, 8))
        self.server_var = tk.StringVar()
        self._focus_entry = ttk.Entry(server, textvariable=self.server_var)
        self._focus_entry.pack(fill="x")
        self._focus_entry.focus_set()
        ttk.Label(
            server,
            text="e.g. http://localhost:11434/v1 (Ollama) or http://localhost:8080/v1 (llama.cpp)",
            style="Dim.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        model_frame = ttk.Frame(frame)
        model_frame.pack(fill="x", pady=(0, 8))
        ttk.Label(model_frame, text="Model").pack(side="left", padx=(0, 8))
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(model_frame, textvariable=self.model_var)
        self.model_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(
            model_frame, text="Fetch Models...", command=self._fetch_models
        ).pack(side="left", padx=(8, 0))

        api = ttk.LabelFrame(frame, text="API Key (optional)", padding=8)
        api.pack(fill="x", pady=(0, 16))
        self.api_key_var = tk.StringVar()
        ttk.Entry(api, textvariable=self.api_key_var, show="*").pack(fill="x")
        ttk.Label(
            api,
            text="Most local servers ignore the key; a placeholder is sent if empty.",
            style="Dim.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self.status_var = tk.StringVar()
        ttk.Label(buttons, textvariable=self.status_var, style="Dim.TLabel").pack(
            side="left"
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            buttons, text="Save", command=self._save, style="Accent.TButton"
        ).pack(side="right")

        self._load()

    def _load(self):
        config = self.master.config
        self.server_var.set(config.data.get("server") or "")
        self.model_var.set(config.data.get("model") or "")
        self.api_key_var.set(config.data.get("api_key") or "")

    def _fetch_models(self):
        server = self.server_var.get().strip()
        if not server:
            self.status_var.set("Enter a server URL first.")
            return
        self.status_var.set("Fetching models...")
        self.update_idletasks()
        try:
            models = fetch_models(server, self.api_key_var.get().strip())
        except ServerError as exc:
            self.status_var.set(f"Could not fetch models: {exc}")
            messagebox.showerror(
                "Server Configuration",
                f"Could not reach the server:\n\n{exc}",
                parent=self,
            )
            return
        self.model_combo["values"] = models
        if models and not self.model_var.get().strip():
            self.model_var.set(models[0])
        self.status_var.set(f"{len(models)} model(s) found.")

    def _save(self):
        server = self.server_var.get().strip()
        model = self.model_var.get().strip()
        if not server:
            self.status_var.set("Enter a server URL.")
            return
        if not model:
            self.status_var.set("Enter a model name.")
            return
        config = self.master.config
        config.data["server"] = server
        config.data["model"] = model
        config.data["api_key"] = self.api_key_var.get().strip()
        config.save()
        if self.on_saved:
            self.on_saved()
        self.destroy()