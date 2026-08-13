"""Theme selector dialog: choose and manage themes."""

import tkinter as tk
from tkinter import messagebox

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme
from kbl.themes import ThemeManager


class ThemeSelectorDialog(tk.Toplevel):
    """Dialog for selecting and managing themes."""

    def __init__(self, master, on_theme_selected=None):
        super().__init__(master)
        self.theme_manager = ThemeManager()
        self.on_theme_selected = on_theme_selected

        self.title("Select Theme")
        self.geometry("450x350")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        self._build_ui()
        self._refresh_list()

    def _build_ui(self):
        # Theme list
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=8, pady=8)

        ttk.Label(list_frame, text="Available Themes:").pack(anchor="w")

        self.listbox = tk.Listbox(list_frame, height=12)
        theme.style_listbox(self.listbox)
        self.listbox.pack(side="left", fill="both", expand=True, pady=(4, 0))

        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y", pady=(4, 0))

        self.listbox.bind("<Double-1>", lambda e: self._apply_selected())

        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=8, pady=8)

        ttk.Button(button_frame, text="Apply", command=self._apply_selected).pack(
            side="left", padx=2
        )
        ttk.Button(button_frame, text="New Theme", command=self._new_theme).pack(
            side="left", padx=2
        )
        ttk.Button(button_frame, text="Edit", command=self._edit_selected).pack(
            side="left", padx=2
        )
        ttk.Button(button_frame, text="Delete", command=self._delete_selected).pack(
            side="left", padx=2
        )
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(
            side="left", padx=2
        )

    def _refresh_list(self):
        self.theme_manager.refresh()
        self.listbox.delete(0, tk.END)
        themes = self.theme_manager.list_themes()
        for theme_name in themes:
            is_builtin = self.theme_manager.is_builtin(theme_name)
            label = f"{theme_name}{' (builtin)' if is_builtin else ''}"
            self.listbox.insert(tk.END, label)

    def _selected_theme(self):
        selection = self.listbox.curselection()
        if not selection:
            return None
        label = self.listbox.get(selection[0])
        # Extract theme name (remove " (builtin)" suffix if present)
        name = label.split(" (builtin)")[0]
        return name.strip()

    def _apply_selected(self):
        name = self._selected_theme()
        if name is None:
            return
        if self.on_theme_selected:
            self.on_theme_selected(name)
        self.destroy()

    def _new_theme(self):
        from kbl.dialogs.theme_editor import ThemeEditorDialog

        dialog = ThemeEditorDialog(self)
        self.wait_window(dialog)
        self._refresh_list()

    def _edit_selected(self):
        name = self._selected_theme()
        if name is None:
            return
        if self.theme_manager.is_builtin(name):
            messagebox.showinfo(
                "Edit", f"'{name}' is a builtin theme. Create a new theme to customize."
            )
            return

        from kbl.dialogs.theme_editor import ThemeEditorDialog

        dialog = ThemeEditorDialog(self, theme_name=name)
        self.wait_window(dialog)
        self._refresh_list()

    def _delete_selected(self):
        name = self._selected_theme()
        if name is None:
            return
        if self.theme_manager.is_builtin(name):
            messagebox.showerror("Delete", "Cannot delete builtin themes.")
            return
        if not messagebox.askyesno("Delete", f"Delete theme '{name}'?"):
            return
        if self.theme_manager.delete_theme(name):
            self._refresh_list()
        else:
            messagebox.showerror("Delete", "Failed to delete theme.")