"""Chat panel: conversation history, input, send/stop, streaming replies."""

import json
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

from kbl import agents, context, theme, tools as kbl_tools, toolstore
from kbl.chat_client import ServerError, chat_stream, fetch_models
from kbl.conversations import ConversationStore, workspace_id_for

_MANAGE_AGENTS_LABEL = "Manage agents..."
_MAX_TOOL_ITERATIONS = 8
_ATTACH_RE = re.compile(r"@([^\s,.;:!?\"'()\[\]{}<>]+)")
_TOOL_PREVIEW_LIMIT = 160
_SUGGESTION_LIMIT = 30


class ChatPanel(ttk.Frame):
    def __init__(self, master, on_configure_server=None, on_manage_agents=None):
        super().__init__(master)
        self.on_configure_server = on_configure_server
        self.on_manage_agents = on_manage_agents
        self.conversation = []
        self._store = ConversationStore()
        self._conv_id = None
        self._conv_name = self._default_conversation_name()
        self._assistant_blocks = []
        self._content_start_mark = None
        self._msg_seq = 0
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
        self._suggest_popup = None
        self._suggest_list = None
        self._suggest_token_start = None
        self._suggest_binding = None

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

        self.history = tk.Text(self, wrap="word", state="disabled")
        self.history.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        theme.style_text(self.history)
        self.history.bind("<Button-3>", self._show_history_menu)

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
        self.input.bind("<KeyRelease>", self._maybe_show_suggestions)
        self.input.bind("<Down>", self._on_suggest_down)
        self.input.bind("<Up>", self._on_suggest_up)
        self.input.bind("<Escape>", self._close_suggestions)

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
        self.history.tag_configure(
            "tool",
            foreground=theme.PALETTE.get("accent", theme.PALETTE["chrome_text"]),
            font=(theme.MONO_FAMILY, theme.SIZE),
        )
        self.history.tag_configure(
            "tool_res",
            foreground=theme.PALETTE.get("chrome_text_dim", theme.PALETTE["chrome_text"]),
            font=(theme.MONO_FAMILY, theme.SIZE - 1),
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
        if self._suggest_popup:
            self._complete_suggestion()
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

        for attached in self._attached_messages(text):
            self.conversation.append(attached)
        self.conversation.append({"role": "user", "content": text})
        self._append("User", text)
        self.persist()
        self._refresh_convs()
        self._start_stream(server, model)

    def _active_workspace(self):
        try:
            workspace = self.master.workspaces.active
        except AttributeError:
            return None
        return str(workspace) if workspace else None

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
            self._append("Attached", token)
        return attached

    def _start_stream(self, server, model):
        api_key = (self.master.config.data.get("api_key") or "").strip()
        self._streaming = True
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._progress_done = False
        self._content_start_mark = None
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
        workspace = self._active_workspace()
        collection = toolstore.collect_tools(workspace, self.master.config)
        tool_list = list(collection.enabled_tools)
        system_prompt = context.compose_system(
            agents.get_prompt(agents.active_agent(self.master.config)),
            context.workspace_instructions(workspace),
            tool_list,
            skills=collection.skills,
        )
        messages = [{"role": "system", "content": system_prompt}] + list(
            self.conversation
        )
        tool_messages = []
        content_parts = []
        call_seq = 0
        try:
            for _round in range(_MAX_TOOL_ITERATIONS):
                calls = None
                for kind, piece in chat_stream(
                    server,
                    model,
                    messages + tool_messages,
                    api_key,
                    self._stop_event,
                    tools=tool_list,
                ):
                    if kind == "tool_calls":
                        calls = piece
                        continue
                    if kind == "content":
                        content_parts.append(piece)
                    self._request_queue.put((kind, piece))
                if calls is None:
                    break
                if self._stop_event is not None and self._stop_event.is_set():
                    break
                normalized = []
                for call in calls:
                    normalized.append(self._normalize_call(call, call_seq))
                    call_seq += 1
                tool_messages.append(self._assistant_tool_message(normalized))
                for call in normalized:
                    result = kbl_tools.run_tool(
                        tool_list, call["name"], call["arguments"]
                    )
                    self._request_queue.put(("tool_call", call))
                    self._request_queue.put(("tool_result", (call, result)))
                    tool_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result,
                        }
                    )
            else:
                self._request_queue.put(
                    ("error", f"Stopped after {_MAX_TOOL_ITERATIONS} tool rounds.")
                )
                return
            final_text = "".join(content_parts)
            if self._stop_event is None or not self._stop_event.is_set():
                self.conversation.extend(tool_messages)
                if final_text:
                    self.conversation.append(
                        {"role": "assistant", "content": final_text}
                    )
            self._request_queue.put(("done", final_text))
        except Exception as exc:
            self._request_queue.put(("error", str(exc)))

    def _normalize_call(self, call, seq):
        return {
            "id": call.get("id") or f"call_{seq}",
            "name": call.get("name") or "",
            "arguments": call.get("arguments") or "{}",
        }

    def _assistant_tool_message(self, calls):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": call["arguments"],
                    },
                }
                for call in calls
            ],
        }

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
            elif kind == "tool_call":
                self._render_tool_call(value)
            elif kind == "tool_result":
                self._render_tool_result(value)
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
        if self._content_start_mark is None:
            self._msg_seq += 1
            self._content_start_mark = f"_a{self._msg_seq}_s"
            self.history.mark_set(self._content_start_mark, "end-1c")
            self.history.mark_gravity(self._content_start_mark, "left")
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
        self.history.configure(state="normal")
        if (
            self._content_start_mark is not None
            and self.conversation
            and self.conversation[-1].get("role") == "assistant"
            and self.conversation[-1].get("content")
        ):
            end_mark = f"_a{self._msg_seq}_e"
            self.history.mark_set(end_mark, "end-1c")
            self.history.mark_gravity(end_mark, "right")
            self._assistant_blocks.append(
                {
                    "conv_index": len(self.conversation) - 1,
                    "start_mark": self._content_start_mark,
                    "end_mark": end_mark,
                }
            )
        self.history.insert("end", "\n")
        self.history.see("end")
        self.history.configure(state="disabled")
        self.persist()
        self._refresh_convs()

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

    # ---- assistant message editing ----

    def _show_history_menu(self, event):
        if self._streaming:
            return
        block = self._block_at_index(self.history.index(f"@{event.x},{event.y}"))
        if block is None:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Edit assistant message",
            command=lambda b=block: self._edit_message(b),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _block_at_index(self, index):
        for block in self._assistant_blocks:
            if self.history.compare(
                index, ">=", block["start_mark"]
            ) and self.history.compare(index, "<=", block["end_mark"]):
                return block
        return None

    def _edit_message(self, block):
        if self._streaming or block["conv_index"] >= len(self.conversation):
            return
        current = self.conversation[block["conv_index"]].get("content") or ""

        dialog = tk.Toplevel(self)
        dialog.title("Edit assistant message")
        dialog.transient(self)
        dialog.grab_set()

        text = tk.Text(dialog, wrap="word", width=70, height=20)
        theme.style_text(text)
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("1.0", current)
        text.focus_set()
        text.tag_add("sel", "1.0", "end-1c")

        row = ttk.Frame(dialog)
        row.pack(fill="x", padx=8, pady=(0, 8))

        def _save():
            new = text.get("1.0", "end-1c")
            self.conversation[block["conv_index"]]["content"] = new
            self.persist()
            self.history.configure(state="normal")
            self.history.delete(block["start_mark"], block["end_mark"])
            self.history.insert(block["start_mark"], new)
            self.history.mark_set(
                block["end_mark"], f"{block['start_mark']} + {len(new)}c"
            )
            self.history.see(block["start_mark"])
            self.history.configure(state="disabled")
            dialog.destroy()

        def _cancel():
            dialog.destroy()

        ttk.Button(row, text="Cancel", command=_cancel).pack(
            side="right", padx=(4, 0)
        )
        ttk.Button(
            row, text="Save", style="Accent.TButton", command=_save
        ).pack(side="right")
        dialog.bind("<Escape>", lambda e: _cancel())

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
        active = self.master.config.data.get("active_conversation") or {}
        active_id = (active.get(workspace_id) or "").strip()
        if not active_id:
            return
        data = self._store.load(active_id, workspace_id)
        if data is None:
            return
        self.conversation = data.get("messages") or []
        self._conv_id = data["id"]
        self._conv_name = data.get("name") or data["id"]
        self._render_history()
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
        self._render_history()
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
        self._render_history()
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
        self._render_history()
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
        config = self.master.config
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

    def _render_history(self):
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")
        self._assistant_blocks = []
        self._thought_blocks = []
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._content_start_mark = None
        self._msg_seq = 0
        self._thought_seq = 0
        for index, message in enumerate(self.conversation):
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                match = re.match(r"^\[Attached file: ([^\]]+)\]", content or "")
                if match:
                    self._append("Attached", match.group(1))
                elif content:
                    self._append("User", content)
            elif role == "assistant" and isinstance(content, str) and content:
                self._render_assistant(index, content)

    def _render_assistant(self, conv_index, content):
        self.history.configure(state="normal")
        self.history.insert("end", "\nAssistant: ")
        start = self.history.index("end-1c")
        self._msg_seq += 1
        start_mark = f"_a{self._msg_seq}_s"
        self.history.mark_set(start_mark, start)
        self.history.mark_gravity(start_mark, "left")
        self.history.insert("end", content)
        end_mark = f"_a{self._msg_seq}_e"
        self.history.mark_set(end_mark, "end-1c")
        self.history.mark_gravity(end_mark, "right")
        self.history.see("end")
        self.history.configure(state="disabled")
        self._assistant_blocks.append(
            {
                "conv_index": conv_index,
                "start_mark": start_mark,
                "end_mark": end_mark,
            }
        )

    # ---- tool call rendering ----

    def _render_tool_call(self, call):
        self._stop_progress()
        name = call.get("name") or "?"
        try:
            args = json.loads(call.get("arguments") or "{}")
        except (ValueError, TypeError):
            args = None
        if isinstance(args, dict) and args:
            shown = ", ".join(f"{k}={v!r}" for k, v in args.items())
        else:
            shown = ""
        self.history.configure(state="normal")
        self.history.insert("end", f"\n  \u2192 {name}({shown})", "tool")
        self.history.see("end")
        self.history.configure(state="disabled")

    def _render_tool_result(self, call_result):
        _call, result = call_result
        preview = " ".join((result or "").split())
        if len(preview) > _TOOL_PREVIEW_LIMIT:
            preview = preview[:_TOOL_PREVIEW_LIMIT] + "\u2026"
        if not preview:
            return
        self.history.configure(state="normal")
        self.history.insert("end", f"\n    {preview}", "tool_res")
        self.history.see("end")
        self.history.configure(state="disabled")

    # ---- @-mention file suggestions ----

    def _suggestion_token(self):
        insert = self.input.index("insert")
        line = insert.split(".")[0]
        line_text = self.input.get(f"{line}.0", "insert")
        idx = line_text.rfind("@")
        if idx < 0:
            return None, None, None
        return line_text[idx + 1 :], f"{line}.{idx}", insert

    def _maybe_show_suggestions(self, event=None):
        if self._streaming:
            self._close_suggestions()
            return
        workspace = self._active_workspace()
        if not workspace:
            self._close_suggestions()
            return
        token, start, _insert = self._suggestion_token()
        if token is None or " " in token:
            self._close_suggestions()
            return
        try:
            files = kbl_tools.list_md_files(workspace)
        except Exception:
            self._close_suggestions()
            return
        lower = token.lower()
        items = [
            f for f in files if f.lower().startswith(lower)
        ][:_SUGGESTION_LIMIT]
        if not items:
            self._close_suggestions()
            return
        self._show_suggestions(items, start)

    def _show_suggestions(self, items, token_start):
        self._close_suggestions()
        top = tk.Toplevel(self)
        top.withdraw()
        top.overrideredirect(True)
        listbox = tk.Listbox(
            top,
            exportselection=False,
            activestyle="dotbox",
            height=min(len(items), 8),
            width=max((len(i) for i in items), default=20) + 2,
        )
        theme.style_listbox(listbox)
        listbox.pack(fill="both", expand=True)
        for item in items:
            listbox.insert("end", item)
        listbox.selection_set(0)
        listbox.activate(0)
        listbox.bind("<ButtonRelease-1>", lambda e: self._complete_suggestion())
        listbox.bind("<Double-Button-1>", lambda e: self._complete_suggestion())
        self._suggest_popup = top
        self._suggest_list = listbox
        self._suggest_token_start = token_start
        self._suggest_binding = self.bind_all("<Button-1>", self._on_popup_click)
        try:
            x, y, _w, h = self.input.bbox("insert")
        except tk.TclError:
            x, y, _w, h = 0, 0, 0, 0
        top.geometry(
            f"+{self.input.winfo_rootx() + x}"
            f"+{self.input.winfo_rooty() + y + h}"
        )
        top.deiconify()
        top.lift()

    def _on_popup_click(self, event):
        if self._suggest_popup is None:
            return
        widget = event.widget
        while widget is not None:
            if widget is self._suggest_popup:
                return
            widget = widget.master
        self._close_suggestions()

    def _complete_suggestion(self):
        if self._suggest_popup is None:
            return
        selection = self._suggest_list.curselection()
        if not selection:
            self._close_suggestions()
            return
        path = self._suggest_list.get(selection[0])
        start = self._suggest_token_start
        self.input.delete(start, "insert")
        self.input.insert(start, path)
        self._close_suggestions()

    def _close_suggestions(self, _event=None):
        if self._suggest_popup is not None:
            try:
                self._suggest_popup.destroy()
            except tk.TclError:
                pass
        if self._suggest_binding is not None:
            try:
                self.unbind_all(self._suggest_binding)
            except tk.TclError:
                pass
        self._suggest_popup = None
        self._suggest_list = None
        self._suggest_token_start = None
        self._suggest_binding = None

    def _on_suggest_down(self, _event=None):
        if self._suggest_popup is None:
            return None
        listbox = self._suggest_list
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        if index < listbox.size() - 1:
            listbox.selection_clear(0, "end")
            listbox.selection_set(index + 1)
            listbox.activate(index + 1)
            listbox.see(index + 1)
        return "break"

    def _on_suggest_up(self, _event=None):
        if self._suggest_popup is None:
            return None
        listbox = self._suggest_list
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        if index > 0:
            listbox.selection_clear(0, "end")
            listbox.selection_set(index - 1)
            listbox.activate(index - 1)
            listbox.see(index - 1)
        return "break"