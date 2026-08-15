"""Tool manager dialog: list, create, rename, delete, and enable/disable tools.

Tools come from three sources (see :mod:`kbl.toolstore`): built-ins shipped in
the app, global tools under ``~/.kbl/tools``, and workspace tools under a
workspace's ``tools`` folder. Selecting a user tool opens its SKILL.md (or
tools.py) in the main editor so it is edited with the existing UI.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme, toolstore, tools as kbl_tools


class ToolManagerDialog(tk.Toplevel):
    """Manage tools grouped by source, with enable/disable controls.

    Left: grouped list of tools (built-ins, global, workspace) with
    New/Rename/Delete/Install Sample. Right: the selected tool's description,
    an Enable/Disable toggle, and buttons to open its SKILL.md or tools.py in
    the main editor.
    """

    def __init__(self, master, on_saved=None):
        super().__init__(master)
        self.on_saved = on_saved

        self.title("Tools")
        self.geometry("720x470")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        self._groups = []  # listbox index -> ("header"|source, name)
        self.build()
        self._refresh_list()

    def build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        left = ttk.Frame(outer)
        left.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(left, text="Tools").pack(anchor="w")
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="y", expand=True, pady=(4, 8))
        self.tool_listbox = tk.Listbox(
            list_frame, height=12, width=30, exportselection=False
        )
        self.tool_listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.tool_listbox.yview
        )
        scroll.pack(side="right", fill="y")
        self.tool_listbox.configure(yscrollcommand=scroll.set)
        self.tool_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select())

        btn_col = ttk.Frame(left)
        btn_col.pack(fill="x")
        ttk.Button(btn_col, text="New Global...", command=self._new_global).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(btn_col, text="New Workspace...", command=self._new_workspace).pack(
            side="left", padx=(0, 4)
        )

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="Rename...", command=self._rename).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(btn_row, text="Delete", command=self._delete).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(btn_row, text="Install Sample", command=self._install_sample).pack(
            side="left"
        )

        right = ttk.Frame(outer)
        right.pack(side="left", fill="both", expand=True)
        self.editor_title = ttk.Label(right, text="Tool", style="Dim.TLabel")
        self.editor_title.pack(anchor="w")
        desc_frame = ttk.Frame(right)
        desc_frame.pack(fill="both", expand=True, pady=(4, 8))
        self.desc_text = tk.Text(desc_frame, wrap="word", state="disabled")
        self.desc_text.pack(side="left", fill="both", expand=True)
        scroll2 = ttk.Scrollbar(
            desc_frame, orient="vertical", command=self.desc_text.yview
        )
        scroll2.pack(side="right", fill="y")
        self.desc_text.configure(yscrollcommand=scroll2.set)
        theme.style_text(self.desc_text)

        actions = ttk.Frame(right)
        actions.pack(fill="x")
        self.status_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.status_var, style="Dim.TLabel").pack(
            side="left"
        )
        self.toggle_btn = ttk.Button(
            actions, text="Disable", command=self._toggle_enabled
        )
        self.toggle_btn.pack(side="right", padx=(8, 0))
        self.open_md_btn = ttk.Button(
            actions, text="Open SKILL.md", command=self._open_skill_md
        )
        self.open_md_btn.pack(side="right", padx=(8, 0))
        ttk.Button(
            actions, text="Open tools.py", command=self._open_tools_py,
            style="Accent.TButton",
        ).pack(side="right")

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Close", command=self.destroy).pack(side="right")
        ttk.Label(
            bottom,
            text="Disabling a tool removes it from the prompt and the model's "
            "schemas (built-ins included). Selected user tools open in the editor.",
            style="Dim.TLabel",
        ).pack(side="left")

    # ---- data ----

    @property
    def _workspace(self):
        try:
            active = self.master.workspaces.active
        except AttributeError:
            return None
        return active

    def _rows(self):
        """Yield (kind, payload) rows: 'header' groups and tool entries.

        ``kind`` is ``"builtin"``, ``"global"``, ``"workspace"``, or
        ``"header"`` (whose payload is the group title).
        """
        workspace = self._workspace

        builtin_names = [t.name for t in kbl_tools.builtin_tools(workspace)]
        global_skills = toolstore.scan_root(toolstore.global_root(), "global")
        ws_skills = toolstore.scan_root(toolstore.workspace_root(workspace), "workspace") if workspace else []

        rows = []
        if builtin_names:
            rows.append(("header", "Built-in tools"))
            rows.extend(("builtin", n) for n in builtin_names)
        if global_skills:
            rows.append(("header", "Global tools"))
            rows.extend(("global", s.folder.name) for s in global_skills)
        if ws_skills:
            rows.append(("header", "Workspace tools"))
            rows.extend(("workspace", s.folder.name) for s in ws_skills)
        return rows

    def _refresh_list(self):
        self.tool_listbox.delete(0, "end")
        self._groups = []
        for kind, payload in self._rows():
            if kind == "header":
                self.tool_listbox.insert("end", f"-- {payload} --")
            else:
                self.tool_listbox.insert("end", payload)
            idx = self.tool_listbox.size() - 1
            self._groups.append((idx, kind, payload))
        self._clear_details()

    def _selected(self, required=True):
        sel = self.tool_listbox.curselection()
        if not sel:
            if required:
                messagebox.showinfo("Tools", "Select a tool first.", parent=self)
            return None
        idx = sel[0]
        for gi, kind, name in self._groups:
            if gi == idx:
                if kind == "header":
                    return None
                return (kind, name)
        return None

    # ---- details ----

    def _clear_details(self):
        self.desc_text.configure(state="normal")
        self.desc_text.delete("1.0", "end")
        self.desc_text.configure(state="disabled")
        self.editor_title.configure(text="Tool")
        self.toggle_btn.configure(state="disabled", text="")
        self.open_md_btn.configure(state="disabled")
        self.status_var.set("")

    def _on_select(self):
        selected = self._selected(required=False)
        if not selected:
            self._clear_details()
            return
        kind, name = selected
        workspace = self._workspace

        skill = None
        if kind in ("global", "workspace"):
            root = toolstore.global_root() if kind == "global" else toolstore.workspace_root(workspace)
            for s in toolstore.scan_root(root, kind):
                if s.folder.name == name:
                    skill = s
                    break

        text = []
        if skill:
            text.append(skill.description or "(no description)")
            text.append("")
            text.append(skill.body)
            if skill.tools:
                text.append("")
                text.append("Tools:")
                for t in skill.tools:
                    text.append(f"  - {t.name}: {t.description}")
            if skill.error:
                text.append("")
                text.append(f"(load error: {skill.error})")
        elif kind == "builtin":
            tool = next((t for t in kbl_tools.builtin_tools(workspace) if t.name == name), None)
            if tool:
                text.append(tool.description)
                if tool.parameters.get("properties"):
                    text.append("")
                    text.append("Parameters:")
                    for pname, spec in tool.parameters["properties"].items():
                        required = pname in tool.parameters.get("required", ())
                        text.append(f"  - {pname}{'' if required else ' (optional)'}: {spec.get('description', '')}")

        self.desc_text.configure(state="normal")
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", "\n".join(text).rstrip() + "\n")
        self.desc_text.configure(state="disabled")
        self.editor_title.configure(text=f"Tool  ({kind} -> {name})")

        disabled = self._is_disabled(name)
        self.toggle_btn.configure(state="normal", text="Enable" if disabled else "Disable")
        can_edit = skill is not None
        self.open_md_btn.configure(state="normal" if can_edit else "disabled")
        self.status_var.set("Disabled" if disabled else "Enabled")

    def _is_disabled(self, name):
        names = self.master.config.data.get("disabled_tools") or []
        return name in names

    # ---- operations ----

    def _toggle_enabled(self):
        selected = self._selected()
        if not selected:
            return
        _, name = selected
        disabled = self._is_disabled(name)
        toolstore.set_disabled(self.master.config, name, not disabled)
        self.status_var.set(f"{name!r} is now {'disabled' if not disabled else 'enabled'}.")
        self._notify()

    def _open_skill_md(self):
        selected = self._selected()
        if not selected:
            return
        kind, name = selected
        self._open_file(kind, name, filename="SKILL.md")

    def _open_tools_py(self):
        selected = self._selected()
        if not selected:
            return
        kind, name = selected
        self._open_file(kind, name, filename="tools.py")

    def _open_file(self, kind, name, filename):
        workspace = self._workspace
        root = toolstore.global_root() if kind == "global" else toolstore.workspace_root(workspace)
        folder = root / name
        editor = getattr(self.master.panels.get("editor"), "open", None)
        if not editor:
            messagebox.showinfo("Tools", "No editor is available.", parent=self)
            return
        editor(str(folder / filename))

    def _new_global(self):
        self._new_tool("global")

    def _new_workspace(self):
        self._new_tool("workspace")

    def _new_tool(self, kind):
        workspace = self._workspace
        root = toolstore.global_root() if kind == "global" else toolstore.workspace_root(workspace)
        name = simpledialog.askstring("New Tool", "Tool name:", parent=self)
        if not name:
            return
        try:
            toolstore.create_skill(root, name)
        except toolstore.ToolStoreError as exc:
            messagebox.showerror("New Tool", str(exc), parent=self)
            return
        self._refresh_list()
        self.status_var.set(f"Created {kind} tool {name!r}.")
        self._notify()

    def _rename(self):
        selected = self._selected()
        if not selected:
            return
        kind, name = selected
        if kind == "builtin":
            messagebox.showinfo("Rename", "Built-in tools cannot be renamed.", parent=self)
            return
        workspace = self._workspace
        root = toolstore.global_root() if kind == "global" else toolstore.workspace_root(workspace)
        new = simpledialog.askstring("Rename Tool", "New name:", initialvalue=name, parent=self)
        if not new:
            return
        try:
            toolstore.rename_skill(root, name, new)
        except toolstore.ToolStoreError as exc:
            messagebox.showerror("Rename Tool", str(exc), parent=self)
            return
        self._refresh_list()
        self.status_var.set(f"Renamed {name!r} to {new!r}.")
        self._notify()

    def _delete(self):
        selected = self._selected()
        if not selected:
            return
        kind, name = selected
        if kind == "builtin":
            messagebox.showinfo("Delete", "Built-in tools cannot be deleted.", parent=self)
            return
        if not messagebox.askyesno(
            "Delete Tool", f"Delete {kind} tool {name!r} and its folder?", parent=self
        ):
            return
        workspace = self._workspace
        root = toolstore.global_root() if kind == "global" else toolstore.workspace_root(workspace)
        try:
            toolstore.delete_skill(root, name)
        except toolstore.ToolStoreError as exc:
            messagebox.showerror("Delete Tool", str(exc), parent=self)
            return
        self._refresh_list()
        self.status_var.set(f"Deleted tool {name!r}.")
        self._notify()

    def _install_sample(self):
        workspace = self._workspace
        samples = ["global", "workspace"]
        if not workspace:
            samples = ["global"]
        target = simpledialog.askstring(
            "Install Sample",
            "Install the sample 'todo' tool into (global or workspace):",
            parent=self,
        )
        if not target:
            return
        target = target.strip().lower()
        if target not in ("global", "workspace"):
            messagebox.showinfo(
                "Install Sample",
                "Enter 'global' for every workspace, or 'workspace' for the "
                "current workspace only.",
                parent=self,
            )
            return
        root = toolstore.global_root() if target == "global" else toolstore.workspace_root(workspace)
        try:
            toolstore.install_sample(root)
        except toolstore.ToolStoreError as exc:
            messagebox.showerror("Install Sample", str(exc), parent=self)
            return
        self._refresh_list()
        self.status_var.set("Installed sample 'todo' tool.")
        self._notify()

    def _notify(self):
        if self.on_saved:
            self.on_saved()