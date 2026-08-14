"""Chat panel: conversation history, input, send/stop, streaming replies."""

import queue
import threading
import tkinter as tk

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import agents, theme
from kbl.chat_client import ServerError, chat_stream, fetch_models

_MANAGE_AGENTS_LABEL = "Manage agents..."


class ChatPanel(ttk.Frame):
    def __init__(self, master, on_configure_server=None, on_manage_agents=None):
        super().__init__(master)
        self.on_configure_server = on_configure_server
        self.on_manage_agents = on_manage_agents
        self.conversation = []
        self._request_queue = queue.Queue()
        self._model_queue = queue.Queue()
        self._model_poll_active = False
        self._stop_event = None
        self._streaming = False
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._thought_blocks = []
        self._thought_seq = 0
        self._progress_done = False

        self._build()
        self._restyle()
        self._refresh_agents()
        self._refresh_models()

    # ---- UI ----

    def _build(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")

        self.status_var = tk.StringVar(value="Not configured")
        ttk.Label(toolbar, textvariable=self.status_var, style="Dim.TLabel").pack(
            side="left", padx=8, pady=4
        )
        server_btn = ttk.Button(
            toolbar, text="Server...", command=self._configure_server
        )
        server_btn.pack(side="right", padx=(0, 4), pady=4)

        combo_row = ttk.Frame(self)
        combo_row.pack(fill="x")
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            combo_row, textvariable=self.model_var, state="readonly", width=18
        )
        self.model_combo.pack(side="left", padx=(8, 8), pady=4)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_selected)
        self.agent_var = tk.StringVar()
        self.agent_combo = ttk.Combobox(
            combo_row, textvariable=self.agent_var, state="readonly", width=16
        )
        self.agent_combo.pack(side="left", padx=(0, 8), pady=4)
        self.agent_combo.bind("<<ComboboxSelected>>", self._on_agent_selected)
        self.progress = ttk.Progressbar(
            combo_row, mode="indeterminate", length=140, maximum=1.0
        )

        self.history = tk.Text(self, wrap="word", state="disabled")
        self.history.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        theme.style_text(self.history)

        entry_row = ttk.Frame(self)
        entry_row.pack(fill="x", padx=4, pady=4)
        self.stop_button = ttk.Button(
            entry_row, text="Stop", width=8, command=self._stop, state="disabled"
        )
        self.stop_button.pack(side="right", padx=(0, 4))
        self.send_button = ttk.Button(
            entry_row, text="Send", width=8, style="Accent.TButton", command=self._send
        )
        self.send_button.pack(side="right", padx=(4, 0))
        self.input = tk.Text(entry_row, height=3, width=30, wrap="word")
        theme.style_text(self.input)
        self.input.pack(side="left", fill="both", expand=True)

        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)

    def _restyle(self):
        theme.style_text(self.history)
        theme.style_text(self.input)
        self.history.tag_configure(
            "who", foreground=theme.PALETTE["accent"],
            font=(theme.FAMILY, theme.SIZE, "bold"),
        )
        self.history.tag_configure(
            "think",
            foreground=theme.PALETTE.get("chrome_text_dim", theme.PALETTE["chrome_text"]),
            font=(theme.FAMILY, theme.SIZE, "italic"),
        )
        self._refresh_status()

    # ---- status / server ----

    def _refresh_status(self):
        config = self.master.config
        server = (config.data.get("server") or "").strip()
        if server:
            self.status_var.set(server)
        else:
            self.status_var.set("Not configured")

    def _refresh_agents(self):
        names = agents.list_agents()
        self.agent_combo["values"] = names + [_MANAGE_AGENTS_LABEL]
        current = agents.active_agent(self.master.config)
        if current in names:
            self.agent_var.set(current)

    def _on_agent_selected(self, _event=None):
        name = self.agent_var.get()
        if name == _MANAGE_AGENTS_LABEL:
            self._restore_agent_selection()
            self._manage_agents()
            return
        if not name:
            return
        config = self.master.config
        config.data["active_agent"] = name
        config.save()

    def _restore_agent_selection(self):
        current = agents.active_agent(self.master.config)
        if current:
            self.agent_var.set(current)

    def _refresh_models(self):
        config = self.master.config
        server = (config.data.get("server") or "").strip()
        if not server:
            current = (config.data.get("model") or "").strip()
            self.model_combo["values"] = [current] if current else []
            self.model_var.set(current)
            return
        api_key = (config.data.get("api_key") or "").strip()

        def _fetch():
            try:
                models = fetch_models(server, api_key)
            except ServerError:
                models = []
            self._model_queue.put(models)

        self._model_poll_active = True
        threading.Thread(target=_fetch, daemon=True).start()
        self._poll_models()

    def _poll_models(self):
        if not self._model_poll_active:
            return
        try:
            models = self._model_queue.get_nowait()
        except queue.Empty:
            self.after(40, self._poll_models)
            return
        self._model_poll_active = False
        self._apply_models(models)

    def _apply_models(self, models):
        current = (self.master.config.data.get("model") or "").strip()
        values = list(models)
        if current and current not in values:
            values.insert(0, current)
        self.model_combo["values"] = values
        if current:
            self.model_var.set(current)

    def _on_model_selected(self, _event=None):
        model = self.model_var.get()
        if not model:
            return
        config = self.master.config
        config.data["model"] = model
        config.save()
        self._refresh_status()

    def _config_saved(self):
        self._refresh_status()
        self._refresh_models()

    def _manage_agents(self):
        if self.on_manage_agents:
            self.on_manage_agents()

    def _configure_server(self):
        self._stop()
        if self.on_configure_server:
            self.on_configure_server()

    # ---- actions ----

    def _on_return(self, event):
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
        else:
            self._send()
            return "break"
        return None

    def _send(self):
        if self._streaming:
            return
        config = self.master.config
        server = (config.data.get("server") or "").strip()
        model = (config.data.get("model") or "").strip()
        if not server or not model:
            self.status_var.set("Configure a server and model first.")
            if self.on_configure_server:
                self.on_configure_server()
            return
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        self.input.delete("1.0", "end")

        self.conversation.append({"role": "user", "content": text})
        self._append("User", text)
        self._start_stream(server, model)

    def _start_stream(self, server, model):
        api_key = (self.master.config.data.get("api_key") or "").strip()
        self._streaming = True
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._progress_done = False
        self._stop_event = threading.Event()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.pack(side="left", padx=(8, 0))
        self.progress.start(20)

        self.history.configure(state="normal")
        self.history.insert("end", "\nAssistant: ")
        self.history.configure(state="disabled")

        thread = threading.Thread(
            target=self._stream_worker,
            args=(server, model, api_key),
            daemon=True,
        )
        thread.start()
        self._drain_queue()

    def _stream_worker(self, server, model, api_key):
        system_prompt = agents.get_prompt(agents.active_agent(self.master.config))
        messages = [{"role": "system", "content": system_prompt}] + list(
            self.conversation
        )
        content_parts = []
        try:
            for kind, piece in chat_stream(
                server, model, messages, api_key, self._stop_event
            ):
                if kind == "content":
                    content_parts.append(piece)
                self._request_queue.put((kind, piece))
            self._request_queue.put(("done", "".join(content_parts)))
        except Exception as exc:
            self._request_queue.put(("error", str(exc)))

    # ---- queue draining (UI thread) ----

    def _drain_queue(self):
        while True:
            try:
                kind, value = self._request_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "reasoning":
                self._append_thinking(value)
            elif kind == "content":
                self._append_stream(value)
            elif kind == "done":
                self._finish_stream(value)
            elif kind == "error":
                self._append("Error", value)
                self._finish_stream("", error=True)
        if self._streaming:
            self.after(40, self._drain_queue)

    def _append_thinking(self, piece):
        self._stop_progress()
        if self._thinking_start is None:
            self._thinking_start = self.history.index("end-1c")
        self._thinking_text.append(piece)
        self.history.configure(state="normal")
        self.history.insert("end", piece, "think")
        self.history.see("end")
        self.history.configure(state="disabled")

    def _append_stream(self, piece):
        self._stop_progress()
        if not self._thinking_collapsed and self._thinking_text:
            self._collapse_thinking()
        self.history.configure(state="normal")
        self.history.insert("end", piece)
        self.history.see("end")
        self.history.configure(state="disabled")

    def _stop_progress(self):
        if self._progress_done:
            return
        self._progress_done = True
        self.progress.stop()
        self.progress.pack_forget()

    def _collapse_thinking(self):
        self._thinking_collapsed = True
        self._stop_progress()
        thinking = "".join(self._thinking_text)
        if not thinking:
            return
        seq = self._thought_seq
        self._thought_seq += 1
        anchor = self._thinking_start
        toggle = ttk.Button(self.history, text=f"Thought process \u25b8{seq}")
        toggle.configure(command=lambda b=seq: self._toggle_thought(b))
        self._thought_blocks.append(
            {"seq": seq, "button": toggle, "text": thinking,
             "mark": f"_thought{seq}", "shown": False}
        )
        self.history.configure(state="normal")
        self.history.delete(anchor, "end")
        self.history.window_create(anchor, window=toggle)
        self.history.mark_set(f"_thought{seq}", f"{anchor} + 1c")
        self.history.mark_gravity(f"_thought{seq}", "left")
        self.history.configure(state="disabled")

    def _toggle_thought(self, seq):
        block = next(b for b in self._thought_blocks if b["seq"] == seq)
        insert_at = self.history.index(block["mark"])
        self.history.configure(state="normal")
        if block["shown"]:
            end = self.history.index(f"{insert_at} + {len(block['text'])}c")
            self.history.delete(insert_at, end)
            block["shown"] = False
            block["button"].configure(text=f"Thought process \u25b8{seq}")
        else:
            self.history.insert(insert_at, block["text"], "think")
            block["shown"] = True
            block["button"].configure(text=f"Thought process \u25be{seq}")
        self.history.see(insert_at)
        self.history.configure(state="disabled")

    def _finish_stream(self, assistant_text, error=False):
        self._streaming = False
        self._stop_event = None
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._stop_progress()
        if not error and assistant_text:
            self.conversation.append({"role": "assistant", "content": assistant_text})
        self.history.configure(state="normal")
        self.history.insert("end", "\n")
        self.history.see("end")
        self.history.configure(state="disabled")

    def _stop(self):
        if self._stop_event:
            self._stop_event.set()
        self._streaming = False
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._stop_progress()

    # ---- history helpers ----

    def _append(self, who, text):
        self.history.configure(state="normal")
        self.history.insert("end", "\n")
        if who:
            self.history.insert("end", f"{who}: ", "who")
        if text:
            self.history.insert("end", text)
        self.history.see("end")
        self.history.configure(state="disabled")