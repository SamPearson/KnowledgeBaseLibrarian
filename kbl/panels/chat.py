"""Chat panel: conversation history, input, send/stop, streaming replies."""

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import agents, theme
from kbl.chat_client import ServerError, fetch_models
from kbl.harness import orchestrate
from kbl.markdown_render import MarkdownRenderer
from kbl.conversations import ConversationStore, workspace_id_for
from kbl.events import (
    DELEGATION_REQUESTED,
    SUBAGENT_COMPLETED,
    SUBAGENT_EVENT,
    SUBAGENT_FAILED,
    SUBAGENT_STARTED,
    AgentManagerRequested,
    ServerConfigRequested,
    WorkspaceSelected,
)

_SUBAGENT_TOPICS = frozenset(
    {
        DELEGATION_REQUESTED,
        SUBAGENT_STARTED,
        SUBAGENT_EVENT,
        SUBAGENT_COMPLETED,
        SUBAGENT_FAILED,
    }
)
from kbl.panels.attach_popup import AttachPopup
from kbl.panels.history_view import HistoryView
from kbl.panels.input_keys import bind_input_keys
from kbl.panels.message_dialogs import (
    delete_message_dialog,
    edit_message_dialog,
)

_MANAGE_AGENTS_LABEL = "Manage agents..."
_ATTACH_RE = re.compile(r"@([^\s,.;:!?\"'()\[\]{}<>]+)")


class ChatPanel(ttk.Frame):
    def __init__(self, master, config, bus=None, harness=None, renderer=None):
        super().__init__(master)
        self.config = config
        self.bus = bus
        self._harness = harness if harness is not None else orchestrate
        self._renderer = renderer if renderer is not None else MarkdownRenderer()
        self.workspace = None
        if bus is not None:
            bus.subscribe("workspace_selected", self._on_workspace_selected)

        self.conversation = []
        self._store = ConversationStore()
        self._conv_id = None
        self._conv_name = self._default_conversation_name()
        self._request_queue = queue.Queue()
        self._model_queue = queue.Queue()
        self._model_poll_active = False
        self._stop_event = None
        self._streaming = False
        self._progress_done = False

        self._build()
        self._restyle()
        self._refresh_agents()
        self._refresh_models()
        self._restore_conversation()

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
        self.conv_var = tk.StringVar()
        self.conv_combo = ttk.Combobox(
            combo_row, textvariable=self.conv_var, state="readonly", width=28
        )
        self.conv_combo.pack(side="left", padx=(0, 8), pady=4)
        self.conv_combo.bind("<<ComboboxSelected>>", self._on_conv_selected)
        self.new_conv_btn = ttk.Button(
            combo_row, text="New", width=5, command=self._new_conversation
        )
        self.new_conv_btn.pack(side="left", padx=(0, 4), pady=4)
        self.rename_conv_btn = ttk.Button(
            combo_row, text="Rename", width=8, command=self._rename_conversation
        )
        self.rename_conv_btn.pack(side="left", padx=(0, 8), pady=4)
        self.progress = ttk.Progressbar(
            combo_row, mode="indeterminate", length=140, maximum=1.0
        )

        self.pw = ttk.Panedwindow(self, orient="vertical")
        self.pw.pack(fill="both", expand=True, padx=4, pady=(4, 0))

        self.view = HistoryView(
            self.pw,
            on_edit=self._edit_message,
            on_delete=self._delete_message,
            stop_progress=self._stop_progress,
            renderer=self._renderer,
        )
        self.pw.add(self.view.widget, weight=1)

        entry_pane = ttk.Frame(self.pw)
        entry_row = ttk.Frame(entry_pane)
        entry_row.pack(fill="both", expand=True, padx=4, pady=4)
        self.stop_button = ttk.Button(
            entry_row, text="Stop", width=8, command=self._stop, state="disabled"
        )
        self.stop_button.pack(side="right", padx=(0, 4))
        self.send_button = ttk.Button(
            entry_row, text="Send", width=8, style="Accent.TButton", command=self._send
        )
        self.send_button.pack(side="right", padx=(4, 0))
        self.input = tk.Text(entry_row, height=3, width=30, wrap="word", undo=True)
        theme.style_text(self.input)
        self.input.pack(side="left", fill="both", expand=True)
        self.pw.add(entry_pane, weight=0)

        self.after_idle(self._init_sash)

        self.popup = AttachPopup(
            self.input, self._active_workspace, lambda: self._streaming
        )
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<Shift-Return>", lambda e: None)
        self.input.bind("<KeyRelease>", self.popup.maybe_show)
        self.input.bind("<Down>", self.popup.down)
        self.input.bind("<Up>", self.popup.up)
        self.input.bind("<Escape>", self.popup.close)
        bind_input_keys(self.input)

    def _init_sash(self):
        if len(self.pw.panes()) < 2:
            return
        total = self.pw.winfo_height()
        if total > 1:
            self.pw.sashpos(0, max(60, total - 120))

    def _restyle(self):
        self.view.restyle()
        theme.style_text(self.input)
        self._refresh_status()

    # ---- status / server ----

    def _refresh_status(self):
        config = self.config
        server = (config.data.get("server") or "").strip()
        if server:
            self.status_var.set(server)
        else:
            self.status_var.set("Not configured")

    def _refresh_agents(self):
        names = agents.list_agents()
        self.agent_combo["values"] = names + [_MANAGE_AGENTS_LABEL]
        current = agents.active_agent(self.config)
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
        config = self.config
        config.data["active_agent"] = name
        config.save()

    def _restore_agent_selection(self):
        current = agents.active_agent(self.config)
        if current:
            self.agent_var.set(current)

    def _refresh_models(self):
        config = self.config
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
        current = (self.config.data.get("model") or "").strip()
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
        config = self.config
        config.data["model"] = model
        config.save()
        self._refresh_status()

    def _config_saved(self):
        self._refresh_status()
        self._refresh_models()

    def _manage_agents(self):
        if self.bus is not None:
            self.bus.emit(AgentManagerRequested())

    def _configure_server(self):
        self._stop()
        if self.bus is not None:
            self.bus.emit(ServerConfigRequested())

    # ---- actions ----

    def _on_return(self, event):
        if self.popup.active:
            self.popup.complete()
            return "break"
        if event.state & 0x0001:
            self.input.insert("insert", "\n")
        else:
            self._send()
            return "break"
        return None

    def _send(self):
        if self._streaming:
            return
        config = self.config
        server = (config.data.get("server") or "").strip()
        model = (config.data.get("model") or "").strip()
        if not server or not model:
            self.status_var.set("Configure a server and model first.")
            if self.bus is not None:
                self.bus.emit(ServerConfigRequested())
            return
        text = self.input.get("1.0", "end-1c").strip()
        if not text:
            return
        self.input.delete("1.0", "end")

        for attached in self._attached_messages(text):
            self.conversation.append(attached)
        self.conversation.append({"role": "user", "content": text})
        self.view.append("User", text, len(self.conversation) - 1)
        self.persist()
        self._refresh_convs()
        self._start_stream(server, model)

    def _active_workspace(self):
        return str(self.workspace) if self.workspace else None

    def _on_workspace_selected(self, payload):
        self.workspace = payload.workspace
        self._on_workspace_changed()

    def _current_workspace_id(self):
        return workspace_id_for(self._active_workspace())

    def _attached_messages(self, text):
        workspace = self._active_workspace()
        if not workspace:
            return []
        base = Path(workspace)
        attached = []
        seen = []
        for token in _ATTACH_RE.findall(text):
            token = token.rstrip(".,;:!?")
            if not token or token in seen:
                continue
            target = (base / token).resolve()
            if target != base and base not in target.parents:
                continue
            if not target.is_file():
                continue
            seen.append(token)
            try:
                contents = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            attached.append(
                {
                    "role": "user",
                    "content": f"[Attached file: {token}]\n\n{contents}",
                }
            )
            self.view.append("Attached", token)
        return attached

    def _start_stream(self, server, model):
        api_key = (self.config.data.get("api_key") or "").strip()
        self._streaming = True
        self._progress_done = False
        self._stop_event = threading.Event()
        self.view.reset_stream_state()
        self.send_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.progress.pack(side="left", padx=(8, 0))
        self.progress.start(20)

        self.view.start_stream()

        thread = threading.Thread(
            target=self._stream_worker,
            args=(server, model, api_key),
            daemon=True,
        )
        thread.start()
        self._drain_queue()

    def _stream_worker(self, server, model, api_key):
        workspace = self._active_workspace()
        try:
            for event in self._harness(
                server,
                model,
                api_key,
                self.conversation,
                workspace=workspace,
                config=self.config,
                stop_event=self._stop_event,
                event_sink=self._event_sink,
            ):
                self._request_queue.put(event)
        except Exception as exc:
            self._request_queue.put(("error", str(exc)))

    def _event_sink(self, kind, value):
        self._request_queue.put((kind, value))

    # ---- queue draining (UI thread) ----

    def _drain_queue(self):
        while True:
            try:
                kind, value = self._request_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "reasoning":
                self.view.append_thinking(value)
            elif kind == "content":
                self.view.append_stream(value)
            elif kind == "tool_call":
                self.view.render_tool_call(value)
            elif kind == "tool_result":
                self.view.render_tool_result(value)
            elif kind == "done":
                self._finish_stream(value)
            elif kind == "error":
                self.view.append("Error", value)
                self._finish_stream("", error=True)
            elif kind in _SUBAGENT_TOPICS:
                self._relay_subagent_event(value)
        if self._streaming:
            self.after(40, self._drain_queue)

    def _stop_progress(self):
        if self._progress_done:
            return
        self._progress_done = True
        self.progress.stop()
        self.progress.pack_forget()

    def _finish_stream(self, assistant_text, error=False):
        self._streaming = False
        self._stop_event = None
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._stop_progress()
        self.view.finish(self.conversation)
        self.persist()
        self._refresh_convs()

    def _relay_subagent_event(self, payload):
        if self.bus is not None:
            self.bus.emit(payload)

    def _stop(self):
        if self._stop_event:
            self._stop_event.set()
        self._streaming = False
        self.send_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._stop_progress()

    # ---- message editing ----

    def _edit_message(self, conv_index, role):
        def _commit(new_content):
            self.conversation[conv_index]["content"] = new_content
            self.persist()
            view = self.view.widget.yview()
            self.view.render_history(self.conversation)
            self.view.widget.yview_moveto(view[0])

        edit_message_dialog(
            self,
            self.conversation,
            conv_index,
            role,
            on_commit=_commit,
            stream_check=lambda: self._streaming,
        )

    def _delete_message(self, conv_index):
        delete_message_dialog(
            self,
            self.conversation,
            conv_index,
            on_confirm=lambda: self._delete_from(conv_index),
            stream_check=lambda: self._streaming,
        )

    def _delete_from(self, conv_index):
        del self.conversation[conv_index:]
        self.persist()
        view = self.view.widget.yview()
        self.view.render_history(self.conversation)
        self.view.widget.yview_moveto(view[0])

    # ---- conversation store ----

    def _default_conversation_name(self):
        existing = {
            c["name"]
            for c in self._store.list_conversations(self._current_workspace_id())
        }
        n = 1
        while f"Conversation {n}" in existing:
            n += 1
        return f"Conversation {n}"

    def _refresh_convs(self):
        values = [
            c["name"]
            for c in self._store.list_conversations(self._current_workspace_id())
        ]
        self.conv_combo["values"] = values
        state = "normal" if self._conv_id is not None else "disabled"
        self.rename_conv_btn.configure(state=state)
        self.conv_var.set(self._conv_name)

    def _restore_conversation(self):
        self._refresh_convs()
        workspace_id = self._current_workspace_id()
        active = self.config.data.get("active_conversation") or {}
        active_id = (active.get(workspace_id) or "").strip()
        if not active_id:
            return
        data = self._store.load(active_id, workspace_id)
        if data is None:
            return
        self.conversation = data.get("messages") or []
        self._conv_id = data["id"]
        self._conv_name = data.get("name") or data["id"]
        self.view.render_history(self.conversation)
        self._refresh_convs()

    def _on_conv_selected(self, _event=None):
        name = self.conv_var.get()
        if not name:
            return
        workspace_id = self._current_workspace_id()
        conv = self._store.find_by_name(name, workspace_id)
        if conv is None or conv["id"] == self._conv_id:
            self._refresh_convs()
            return
        if self._streaming:
            self._stop()
            self._refresh_convs()
            return
        self.persist()
        data = self._store.load(conv["id"], workspace_id)
        if data is None:
            self._refresh_convs()
            return
        self.conversation = data.get("messages") or []
        self._conv_id = data["id"]
        self._conv_name = data.get("name") or data["id"]
        self.view.render_history(self.conversation)
        self._refresh_convs()
        self._update_active_conversation()

    def _new_conversation(self):
        if self._streaming:
            self._stop()
            self._refresh_convs()
            return
        self.persist()
        self.conversation = []
        self._conv_id = None
        self._conv_name = self._default_conversation_name()
        self.view.render_history(self.conversation)
        self._refresh_convs()
        self._update_active_conversation()

    def _on_workspace_changed(self):
        if self._streaming:
            self._stop()
            self._refresh_convs()
            return
        self.conversation = []
        self._conv_id = None
        self._conv_name = self._default_conversation_name()
        self.view.render_history(self.conversation)
        self._refresh_convs()
        self._restore_conversation()

    def _rename_conversation(self):
        if self._conv_id is None:
            return
        name = simpledialog.askstring(
            "Rename conversation",
            "Name:",
            initialvalue=self._conv_name,
            parent=self,
        )
        if not name or not name.strip():
            return
        name = name.strip()
        if name == self._conv_name:
            return
        workspace_id = self._current_workspace_id()
        if self._store.name_exists(name, workspace_id):
            messagebox.showwarning(
                "Rename conversation",
                f'A conversation named "{name}" already exists.',
                parent=self,
            )
            return
        self._conv_name = name
        self._store.rename(self._conv_id, name, workspace_id)
        self._refresh_convs()

    def _update_active_conversation(self):
        config = self.config
        active = config.data.get("active_conversation")
        if not isinstance(active, dict):
            active = {}
            config.data["active_conversation"] = active
        active[self._current_workspace_id()] = self._conv_id
        config.save()

    def persist(self):
        if not self.conversation and self._conv_id is None:
            return
        conversation = {
            "id": self._conv_id,
            "name": self._conv_name,
            "messages": self.conversation,
        }
        self._conv_id = self._store.save(
            conversation, self._current_workspace_id()
        )
        self._update_active_conversation()