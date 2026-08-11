"""Main window: menubar, panel layout presets, and wiring."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from kbl.panels.chat import ChatPanel
from kbl.panels.editor import EditorPanel
from kbl.panels.file_tree import FileTreePanel
from kbl.workspaces import WorkspaceManager

LAYOUTS = {
    "tree-editor-chat": ("tree", "editor", "chat"),
    "tree-editor": ("tree", "editor"),
    "editor-chat": ("editor", "chat"),
    "editor": ("editor",),
}
DEFAULT_LAYOUT = "tree-editor-chat"
MIN_PANE_WIDTH = 20


class MainWindow(tk.Tk):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.workspaces = WorkspaceManager(config)

        self.title("Knowledge Base Librarian")
        self.geometry("1200x800")

        self.panels = {}
        self._layout_var = tk.StringVar(value=config.data["layout"])

        self._build_panels()
        self._build_menus()
        self._apply_layout(config.data["layout"])

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._schedule_restore()

        active = self.workspaces.active
        if active:
            self.panels["tree"].set_workspace(active)

    # ---- panels ----

    def _build_panels(self):
        self._layout_widget = ttk.PanedWindow(self, orient="horizontal")
        self._layout_widget.pack(fill="both", expand=True)
        self.panels["tree"] = FileTreePanel(self, on_open=self._open_file)
        self.panels["editor"] = EditorPanel(self, config=self.config)
        self.panels["chat"] = ChatPanel(self)

    def _open_file(self, path):
        self.panels["editor"].open(path)

    # ---- layout ----

    def _apply_layout(self, name):
        if name not in LAYOUTS:
            name = DEFAULT_LAYOUT
        for panel in self.panels.values():
            try:
                self._layout_widget.forget(panel)
            except tk.TclError:
                pass
        for key in LAYOUTS[name]:
            self._layout_widget.add(self.panels[key], weight=1)
        self.config.data["layout"] = name
        self._layout_var.set(name)

    def _switch_layout(self, name):
        self._save_sizes()
        self._apply_layout(name)
        self._schedule_restore()

    def _save_sizes(self):
        if self._layout_widget is None:
            return
        positions = []
        for index in range(len(self._layout_widget.panes()) - 1):
            try:
                positions.append(
                    max(MIN_PANE_WIDTH, int(self._layout_widget.sashpos(index)))
                )
            except tk.TclError:
                break
        self.config.data["panel_sizes"][self.config.data["layout"]] = positions

    def _schedule_restore(self):
        self.after(50, self._restore_when_ready)

    def _restore_when_ready(self):
        widget = self._layout_widget
        if widget is None:
            return
        if not widget.winfo_ismapped() or widget.winfo_width() < 2:
            self._schedule_restore()
            return
        positions = self.config.data["panel_sizes"].get(
            self.config.data["layout"], []
        )
        if positions:
            for index, position in enumerate(positions):
                if position < MIN_PANE_WIDTH:
                    continue
                try:
                    widget.sashpos(index, position)
                except tk.TclError:
                    break
        else:
            self._normalize_layout(widget)

    def _normalize_layout(self, widget):
        panes = widget.panes()
        count = len(panes)
        if count < 2:
            return
        total = widget.winfo_width()
        for index in range(count - 1):
            try:
                widget.sashpos(index, int(total * (index + 1) / count))
            except tk.TclError:
                break

    # ---- menus ----

    def _build_menus(self):
        menubar = tk.Menu(self)
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Markdown File...", command=self._new_file)
        file_menu.add_command(label="New Folder...", command=self._new_folder)
        file_menu.add_command(label="Save", command=self.panels["editor"].save)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        workspace_menu = tk.Menu(menubar, tearoff=0)
        workspace_menu.add_command(
            label="Open Folder...", command=self._add_workspace
        )
        workspace_menu.add_command(
            label="Workspaces...", command=self._show_workspace_dialog
        )
        workspace_menu.add_separator()
        self.workspace_menu = workspace_menu
        menubar.add_cascade(label="Workspace", menu=workspace_menu)
        self._update_workspace_menu()

        view_menu = tk.Menu(menubar, tearoff=0)
        for name in LAYOUTS:
            view_menu.add_radiobutton(
                label=name,
                value=name,
                variable=self._layout_var,
                command=lambda n=name: self._switch_layout(n),
            )
        view_menu.add_separator()
        view_menu.add_command(
            label="Toggle Edit/Display",
            command=self.panels["editor"].toggle_mode,
        )
        menubar.add_cascade(label="View", menu=view_menu)

    def _update_workspace_menu(self):
        menu = self.workspace_menu
        menu.delete(3, "end")
        for path in self.workspaces.workspaces:
            label = path.name or str(path)
            active = self.workspaces.active
            if active and path == active:
                label = f"\u25b8 {label}"
            menu.add_command(
                label=label,
                command=lambda p=path: self._activate_workspace(p),
            )

    # ---- workspace actions ----

    def _add_workspace(self):
        path = filedialog.askdirectory(title="Choose a workspace folder")
        if not path:
            return
        try:
            self.workspaces.add(path)
        except ValueError as exc:
            messagebox.showerror("Workspace", str(exc))
            return
        self._activate_workspace(path)

    def _activate_workspace(self, path):
        self.workspaces.set_active(path)
        self.panels["tree"].set_workspace(path)
        self._update_workspace_menu()

    def _show_workspace_dialog(self):
        WorkspaceDialog(self, self.workspaces, self._activate_workspace)

    # ---- misc actions ----

    def _new_file(self):
        active = self.workspaces.active
        if active is None:
            messagebox.showinfo("New File", "Open a workspace first.")
            return
        self.panels["tree"].new_file()

    def _new_folder(self):
        active = self.workspaces.active
        if active is None:
            messagebox.showinfo("New Folder", "Open a workspace first.")
            return
        self.panels["tree"].new_folder()

    # ---- lifecycle ----

    def _on_close(self):
        self._save_sizes()
        self.config.save()
        self.destroy()


class WorkspaceDialog(tk.Toplevel):
    def __init__(self, master, manager, on_activate):
        super().__init__(master)
        self.manager = manager
        self.on_activate = on_activate

        self.title("Workspaces")
        self.geometry("480x320")
        self.transient(master)
        self.grab_set()

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(frame)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.listbox.yview
        )
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")

        buttons = ttk.Frame(frame)
        buttons.pack(side="left", fill="y", padx=8)
        ttk.Button(buttons, text="Add Folder...", command=self._add).pack(
            fill="x", pady=2
        )
        ttk.Button(buttons, text="Remove", command=self._remove).pack(
            fill="x", pady=2
        )
        ttk.Button(buttons, text="Activate", command=self._activate).pack(
            fill="x", pady=2
        )
        ttk.Button(buttons, text="Close", command=self.destroy).pack(
            fill="x", pady=2
        )

        self._refresh()

    def _refresh(self):
        self.listbox.delete(0, "end")
        active = self.manager.active
        for path in self.manager.workspaces:
            label = str(path)
            if active and path == active:
                label = f"\u25b8 {label}"
            self.listbox.insert("end", label)

    def _selected(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        return self.manager.workspaces[selection[0]]

    def _add(self):
        path = filedialog.askdirectory(title="Choose a workspace folder")
        if not path:
            return
        try:
            self.manager.add(path)
        except ValueError as exc:
            messagebox.showerror("Workspace", str(exc), parent=self)
            return
        self._refresh()

    def _remove(self):
        path = self._selected()
        if path is None:
            return
        if not messagebox.askyesno(
            "Remove", f"Remove {path} from the list?", parent=self
        ):
            return
        self.manager.remove(path)
        if self.manager.active:
            self.on_activate(self.manager.active)
        self._refresh()

    def _activate(self):
        path = self._selected()
        if path is None:
            return
        self.on_activate(path)
        self.destroy()
