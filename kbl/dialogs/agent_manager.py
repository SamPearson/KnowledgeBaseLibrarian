"""Agent manager dialog: create, edit, delete, and select system prompts."""

import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import agents, theme


class AgentManagerDialog(tk.Toplevel):
    """Manage agents stored under ~/.kbl/agents/<name>/system_prompt.md.

    Left: list of agents with New/Rename/Delete. Right: the selected agent's
    system prompt, edited and saved. "Set Active" marks the selected agent as
    the one used for chat. Changes take effect immediately once saved.
    """

    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.on_saved = on_saved

        self.title("Agents")
        self.geometry("680x460")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        self._build()
        self._refresh_list()
        active = agents.active_agent(master.config)
        if active in self.agent_names:
            self.agent_listbox.selection_set(self.agent_names.index(active))
            self._on_select()
        else:
            self._clear_editor()

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="Agents").pack(anchor="w")
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="y", expand=True, pady=(4, 8))
        self.agent_listbox = tk.Listbox(
            list_frame, height=10, width=24, exportselection=False
        )
        self.agent_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.agent_listbox.yview
        )
        scroll.pack(side="right", fill="y")
        self.agent_listbox.configure(yscrollcommand=scroll.set)
        self.agent_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select())

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="New...", command=self._new_agent).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(btn_row, text="Rename...", command=self._rename_agent).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(btn_row, text="Delete", command=self._delete_agent).pack(
            side="left"
        )

        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True)
        self.editor_title = ttk.Label(right, text="System Prompt", style="Dim.TLabel")
        self.editor_title.pack(anchor="w")
        edit_frame = ttk.Frame(right)
        edit_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.prompt_text = tk.Text(edit_frame, wrap="word", undo=True)
        self.prompt_text.pack(side="left", fill="both", expand=True)
        scroll2 = ttk.Scrollbar(
            edit_frame, orient="vertical", command=self.prompt_text.yview
        )
        scroll2.pack(side="right", fill="y")
        self.prompt_text.configure(yscrollcommand=scroll2.set)
        theme.style_text(self.prompt_text)

        actions = ttk.Frame(right)
        actions.pack(fill="x")
        self.status_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.status_var, style="Dim.TLabel").pack(
            side="left"
        )
        ttk.Button(actions, text="Save", command=self._save_prompt).pack(
            side="right", padx=(8, 0)
        )
        ttk.Button(
            actions, text="Set Active", command=self._set_active,
            style="Accent.TButton",
        ).pack(side="right")

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        ttk.Label(
            bottom,
            text="The active agent's system prompt is sent with every message.",
            style="Dim.TLabel",
        ).pack(side="left")

    # ---- state ----

    @property
    def agent_names(self):
        return agents.list_agents()

    def _refresh_list(self):
        self.agent_listbox.delete(0, "end")
        for name in self.agent_names:
            self.agent_listbox.insert("end", name)

    def _selected_agent(self):
        sel = self.agent_listbox.curselection()
        names = self.agent_names
        return names[sel[0]] if sel else None

    def _clear_editor(self):
        self.prompt_text.delete("1.0", "end")
        self.editor_title.configure(text="System Prompt")

    def _on_select(self):
        name = self._selected_agent()
        if not name:
            self._clear_editor()
            return
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", agents.get_prompt(name).rstrip("\n"))
        self.editor_title.configure(text=f"System Prompt  ({name})")

    # ---- operations ----

    def _selected(self, required=True):
        name = self._selected_agent()
        if required and not name:
            messagebox.showinfo("Agents", "Select an agent first.", parent=self)
            return None
        return name

    def _new_agent(self):
        name = simpledialog.askstring("New Agent", "Agent name:", parent=self)
        if not name:
            return
        try:
            agents.create_agent(name)
        except agents.AgentError as exc:
            messagebox.showerror("New Agent", str(exc), parent=self)
            return
        self._refresh_list()
        self.agent_listbox.selection_clear(0, "end")
        self.agent_listbox.selection_set(self.agent_names.index(name))
        self._on_select()
        self.status_var.set(f"Created agent {name!r}.")

    def _rename_agent(self):
        old = self._selected()
        if not old:
            return
        new = simpledialog.askstring(
            "Rename Agent", "New name:", initialvalue=old, parent=self
        )
        if not new:
            return
        try:
            agents.rename_agent(old, new)
        except agents.AgentError as exc:
            messagebox.showerror("Rename Agent", str(exc), parent=self)
            return
        self._refresh_list()
        self.agent_listbox.selection_clear(0, "end")
        self.agent_listbox.selection_set(self.agent_names.index(new))
        self._on_select()
        self.status_var.set(f"Renamed {old!r} to {new!r}.")

    def _delete_agent(self):
        name = self._selected()
        if not name:
            return
        if not messagebox.askyesno(
            "Delete Agent",
            f"Delete agent {name!r} and its system prompt?",
            parent=self,
        ):
            return
        try:
            agents.delete_agent(name)
        except agents.AgentError as exc:
            messagebox.showerror("Delete Agent", str(exc), parent=self)
            return
        config = self.master.config
        if config.data.get("active_agent") == name:
            config.data["active_agent"] = None
        self._refresh_list()
        self._clear_editor()
        self.status_var.set(f"Deleted agent {name!r}.")
        self._notify()

    def _save_prompt(self):
        name = self._selected()
        if not name:
            return
        prompt = self.prompt_text.get("1.0", "end-1c")
        try:
            agents.set_prompt(name, prompt)
        except agents.AgentError as exc:
            messagebox.showerror("Save", str(exc), parent=self)
            return
        self.status_var.set(f"Saved system prompt for {name!r}.")

    def _set_active(self):
        name = self._selected()
        if not name:
            return
        config = self.master.config
        config.data["active_agent"] = name
        config.save()
        self.status_var.set(f"{name!r} is now the active agent.")
        self._notify()

    def _notify(self):
        if self.on_saved:
            self.on_saved()