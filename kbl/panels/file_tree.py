"""File tree panel: mirrors a workspace directory on disk."""

import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme
from kbl.events import FileOpened, WorkspaceSelected


class FileTreePanel(ttk.Frame):
    def __init__(self, master, bus=None):
        super().__init__(master)
        self.bus = bus
        self.workspace = None
        if bus is not None:
            bus.subscribe("workspace_selected", self._on_workspace_selected)

        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        self.workspace_label = ttk.Label(
            bar, text="No workspace", anchor="w", style="Dim.TLabel"
        )
        self.workspace_label.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(bar, text="Refresh", command=self.refresh, width=8).pack(
            side="right", padx=6, pady=4
        )

        self.tree = ttk.Treeview(self, show="tree", selectmode="browse")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(0, 0))
        scroll.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda e: self._open_selected())
        self.tree.bind("<Delete>", lambda e: (self._delete_selected(), "break"))

        self.menu = tk.Menu(self, tearoff=0)
        theme.style_menu(self.menu)
        self.menu.add_command(label="New File...", command=self.new_file)
        self.menu.add_command(label="New Folder...", command=self.new_folder)
        self.menu.add_command(label="Delete", command=self._delete_selected)
        self.menu.add_separator()
        self.menu.add_command(label="Refresh", command=self.refresh)
        self.tree.bind("<Button-3>", self._show_menu)

    def set_workspace(self, path):
        self.workspace = Path(path)
        self.workspace_label.config(text=self.workspace.name)
        self.refresh()

    def _on_workspace_selected(self, payload):
        self.set_workspace(payload.workspace)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        if self.workspace is None:
            return
        self._insert_dir("", self.workspace)

    def _insert_dir(self, parent, path):
        entries = sorted(
            path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
        for child in entries:
            if child.name.startswith("."):
                continue
            if child.is_dir():
                iid = str(child)
                self.tree.insert(parent, "end", iid=iid, text=child.name)
                self._insert_dir(iid, child)
            elif child.suffix.lower() == ".md":
                self.tree.insert(parent, "end", iid=str(child), text=child.name)

    def _selected_path(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return Path(selection[0])

    def _on_double_click(self, _event=None):
        self._open_selected()

    def _open_selected(self):
        path = self._selected_path()
        if path is None:
            return
        if path.is_dir():
            self.tree.item(str(path), open=not self.tree.item(str(path), "open"))
        elif path.is_file():
            if self.bus is not None:
                self.bus.emit(FileOpened(path))
            else:
                self._fallback_open(path)

    def _fallback_open(self, path):
        """Fallback when no bus is wired (kept for headless/tests)."""

    def _show_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
        self.menu.tk_popup(event.x_root, event.y_root)

    def _target_dir(self):
        path = self._selected_path()
        if path is None:
            return self.workspace
        if path.is_dir():
            return path
        return path.parent

    def new_file(self):
        if self.workspace is None:
            messagebox.showinfo("New File", "Open a workspace first.")
            return
        name = simpledialog.askstring(
            "New File",
            "File name (without .md):",
            parent=self,
        )
        if not name:
            return
        if not name.endswith(".md"):
            name += ".md"
        target = self._target_dir() / name
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        except OSError as exc:
            messagebox.showerror("New File", f"Could not create file: {exc}")
            return
        self.refresh()
        self._reveal(target)
        if self.bus is not None:
            self.bus.emit(FileOpened(target))
        else:
            self._fallback_open(target)

    def new_folder(self):
        if self.workspace is None:
            messagebox.showinfo("New Folder", "Open a workspace first.")
            return
        name = simpledialog.askstring(
            "New Folder",
            "Folder name:",
            parent=self,
        )
        if not name:
            return
        target = self._target_dir() / name
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("New Folder", f"Could not create folder: {exc}")
            return
        self.refresh()
        self._reveal(target)

    def _reveal(self, path):
        path = Path(path)
        if path not in (self.workspace,):
            parent = path.parent
            if str(parent) != str(self.workspace):
                ancestors = []
                cur = parent
                while cur != self.workspace:
                    ancestors.append(str(cur))
                    cur = cur.parent
                for iid in reversed(ancestors):
                    self.tree.item(iid, open=True)
        iid = str(path)
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            if path.is_dir():
                self.tree.item(iid, open=True)

    def _delete_selected(self):
        path = self._selected_path()
        if path is None:
            return
        if path == self.workspace:
            return
        if path.is_dir():
            detail = f"folder {path.name} and everything in it"
        elif path.is_file():
            detail = f"file {path.name}"
        else:
            return
        if not messagebox.askyesno(
            "Delete", f"Delete {detail}?", parent=self
        ):
            return
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            messagebox.showerror("Delete", f"Could not delete: {exc}")
            return
        self.refresh()

    def _restyle(self):
        """Re-apply theme styling."""
        theme.style_menu(self.menu)