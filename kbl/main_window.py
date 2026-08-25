"""Main window: menubar, panel layout presets, and wiring."""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    from tkinter import ttk
    TTKBOOTSTRAP_AVAILABLE = False

from kbl import theme
from kbl.panels.chat import ChatPanel
from kbl.panels.editor import EditorPanel
from kbl.panels.file_tree import FileTreePanel
from kbl.workspaces import WorkspaceManager
from kbl.dialogs.server_config import ServerConfigDialog
from kbl.dialogs.agent_manager import AgentManagerDialog
from kbl.dialogs.theme_selector import ThemeSelectorDialog
from kbl.dialogs.tool_manager import ToolManagerDialog

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
        self.geometry("1280x820")

        # Apply theme from config
        theme.apply(self, config.data.get("active_theme", "dark"))

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
        # Note: ttkbootstrap uses Panedwindow (lowercase 'w'), not PanedWindow
        self._layout_widget = ttk.Panedwindow(self, orient="horizontal")
        self._layout_widget.pack(fill="both", expand=True)
        self.panels["tree"] = FileTreePanel(self, on_open=self._open_file)
        self.panels["editor"] = EditorPanel(self, config=self.config)
        self.panels["chat"] = ChatPanel(
            self,
            on_configure_server=self._show_server_config,
            on_manage_agents=self._show_agent_manager,
        )

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
        widget = self._layout_widget
        if widget is None:
            return
        positions = []
        width = widget.winfo_width()
        for index in range(len(widget.panes()) - 1):
            try:
                positions.append(
                    max(MIN_PANE_WIDTH, int(widget.sashpos(index)))
                )
            except tk.TclError:
                break
        self.config.data["panel_sizes"][self.config.data["layout"]] = {
            "width": width,
            "sashes": positions,
        }

    def _schedule_restore(self):
        self.after(50, self._restore_when_ready)

    def _restore_when_ready(self):
        widget = self._layout_widget
        if widget is None:
            return
        if not widget.winfo_ismapped() or widget.winfo_width() < 2:
            self._schedule_restore()
            return
        panes = widget.panes()
        count = len(panes)
        if count < 2:
            return
        width = widget.winfo_width()
        positions = self._resolve_positions(
            self.config.data["panel_sizes"].get(self.config.data["layout"]),
            width,
            count,
        )
        if positions is None:
            self._normalize_layout(widget)
            return
        for index, position in enumerate(positions):
            try:
                widget.sashpos(index, position)
            except tk.TclError:
                break

    def _resolve_positions(self, saved, width, count):
        """Validate saved sash positions for the current window size.

        Scales positions captured at a different window width and rejects
        positions that would leave any pane narrower than MIN_PANE_WIDTH.
        Returns a list of sash positions, or None if the saved positions
        cannot be used (the caller then normalizes the layout).
        """
        if not saved:
            return None
        if isinstance(saved, dict):
            sashes = saved.get("sashes") or []
            saved_width = saved.get("width") or 0
        else:
            sashes = saved
            saved_width = 0
        if len(sashes) != count - 1:
            return None
        if saved_width > 0 and saved_width != width:
            scale = width / saved_width
            sashes = [int(round(pos * scale)) for pos in sashes]
        else:
            sashes = [int(pos) for pos in sashes]
        bounds = [0] + sashes + [width]
        for left, right in zip(bounds, bounds[1:]):
            if right - left < MIN_PANE_WIDTH:
                return None
        return sashes

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
        theme.style_menubar(menubar)
        self.configure(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        theme.style_menu(file_menu)
        file_menu.add_command(label="New Markdown File...", command=self._new_file)
        file_menu.add_command(label="New Folder...", command=self._new_folder)
        file_menu.add_command(label="Save", command=self.panels["editor"].save)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu  # Store reference

        workspace_menu = tk.Menu(menubar, tearoff=0)
        theme.style_menu(workspace_menu)
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
        theme.style_menu(view_menu)
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
        self.view_menu = view_menu  # Store reference

        theme_menu = tk.Menu(menubar, tearoff=0)
        theme.style_menu(theme_menu)
        theme_menu.add_command(label="Select Theme...", command=self._select_theme)
        theme_menu.add_command(label="Edit Theme...", command=self._edit_theme)
        menubar.add_cascade(label="Theme", menu=theme_menu)
        self.theme_menu = theme_menu  # Store reference

        chat_menu = tk.Menu(menubar, tearoff=0)
        theme.style_menu(chat_menu)
        chat_menu.add_command(
            label="Server Configuration...", command=self._show_server_config
        )
        chat_menu.add_command(label="Agents...", command=self._show_agent_manager)
        chat_menu.add_command(label="Tools...", command=self._show_tool_manager)
        menubar.add_cascade(label="Chat", menu=chat_menu)
        self.chat_menu = chat_menu  # Store reference

        self.menubar = menubar  # Store menubar reference

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

    # ---- theme actions ----

    def _select_theme(self):
        ThemeSelectorDialog(self, on_theme_selected=self._apply_theme)

    def _edit_theme(self):
        from kbl.dialogs.theme_editor import ThemeEditorDialog
        current = self.config.data.get("active_theme", "dark")
        ThemeEditorDialog(self, theme_name=current)

    def _apply_theme(self, theme_name):
        """Apply a theme and update all panels."""
        self.config.data["active_theme"] = theme_name
        theme.apply(self, theme_name)

        # Re-style all panels
        self._restyle_panels()
        self._restyle_menus()

    def _restyle_panels(self):
        """Re-apply theme styling to all panels."""
        if "tree" in self.panels:
            self.panels["tree"]._restyle()
        if "editor" in self.panels:
            self.panels["editor"]._restyle()
        if "chat" in self.panels:
            self.panels["chat"]._restyle()

    def _restyle_menus(self):
        """Re-apply theme styling to menus."""
        if hasattr(self, 'menubar'):
            theme.style_menubar(self.menubar)
        if hasattr(self, 'file_menu'):
            theme.style_menu(self.file_menu)
        if hasattr(self, 'workspace_menu'):
            theme.style_menu(self.workspace_menu)
        if hasattr(self, 'view_menu'):
            theme.style_menu(self.view_menu)
        if hasattr(self, 'theme_menu'):
            theme.style_menu(self.theme_menu)
        if hasattr(self, 'chat_menu'):
            theme.style_menu(self.chat_menu)

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
        self.panels["chat"].persist()
        # User-initiated switch: make it this instance's active workspace and
        # persist it as the default for future no---workspace launches.
        self.workspaces.set_active(path, persist_default=True)
        self.panels["tree"].set_workspace(path)
        self.panels["chat"]._on_workspace_changed()
        self._update_workspace_menu()

    def _show_workspace_dialog(self):
        WorkspaceDialog(self, self.workspaces, self._activate_workspace)

    # ---- chat actions ----

    def _show_server_config(self):
        ServerConfigDialog(
            self,
            on_saved=self.panels["chat"]._config_saved,
        )

    def _show_agent_manager(self):
        AgentManagerDialog(
            self,
            on_saved=self._after_agents_change,
        )

    def _after_agents_change(self):
        chat = self.panels["chat"]
        chat._refresh_agents()

    def _show_tool_manager(self):
        ToolManagerDialog(
            self,
            on_saved=self._after_tools_change,
        )

    def _after_tools_change(self):
        chat = self.panels["chat"]
        chat._refresh_agents()

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
        self.panels["chat"].persist()
        self.config.save()
        self.destroy()


class WorkspaceDialog(tk.Toplevel):
    def __init__(self, master, manager, on_activate):
        super().__init__(master)
        self.manager = manager
        self.on_activate = on_activate

        self.title("Workspaces")
        self.geometry("520x340")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        frame = ttk.Frame(self, padding=8)
        frame.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(frame)
        theme.style_listbox(self.listbox)
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