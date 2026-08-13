"""Theme editor dialog: create and edit custom themes."""

import tkinter as tk
from tkinter import colorchooser, messagebox

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import theme
from kbl.themes import ThemeManager

PALETTE_FIELDS = [
    ("window_bg", "Window Background"),
    ("slate_bg", "Panel Background"),
    ("slate_alt", "Panel Alt Background"),
    ("border", "Border Color"),
    ("chrome_text", "Panel Text"),
    ("chrome_text_dim", "Panel Text (Dim)"),
    ("parchment_bg", "Editor Background"),
    ("parchment_alt", "Editor Alt Background"),
    ("ink", "Editor Text"),
    ("ink_soft", "Editor Text (Soft)"),
    ("accent", "Accent Color"),
    ("accent_hover", "Accent Hover"),
    ("accent_text", "Accent Text"),
]


class ThemeEditorDialog(tk.Toplevel):
    """Dialog for editing and saving themes."""

    def __init__(self, master, theme_name=None):
        super().__init__(master)
        self.theme_manager = ThemeManager()
        self.theme_name = theme_name
        self.palette = {}
        self.color_buttons = {}

        self.title("Theme Editor" if theme_name is None else f"Edit Theme: {theme_name}")
        self.geometry("500x700")
        self.transient(master)
        self.grab_set()
        self.configure(bg=theme.PALETTE["window_bg"])

        # Load existing theme if editing
        if theme_name:
            self.theme_manager.refresh()
            existing = self.theme_manager.get_theme(theme_name)
            if existing:
                self.palette = existing.copy()
            else:
                self.palette = theme.PALETTE.copy()
        else:
            self.palette = theme.PALETTE.copy()

        self._build_ui()

    def _build_ui(self):
        # Theme name
        name_frame = ttk.Frame(self)
        name_frame.pack(fill="x", padx=12, pady=8)
        ttk.Label(name_frame, text="Theme Name:").pack(side="left", padx=(0, 8))
        self.name_var = tk.StringVar(value=self.theme_name or "")
        name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        name_entry.pack(side="left", fill="x", expand=True)

        # Colors
        scroll_frame = ttk.Frame(self)
        scroll_frame.pack(fill="both", expand=True, padx=8, pady=8)

        canvas = tk.Canvas(
            scroll_frame,
            bg=theme.PALETTE["slate_bg"],
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(scroll_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        for key, label in PALETTE_FIELDS:
            self._add_color_row(scrollable_frame, key, label)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", padx=8, pady=8, side="bottom")
        ttk.Button(button_frame, text="Save", command=self._save).pack(side="left", padx=2)
        ttk.Button(button_frame, text="Reset", command=self._reset).pack(side="left", padx=2)
        ttk.Button(button_frame, text="Cancel", command=self.destroy).pack(side="left", padx=2)

    def _add_color_row(self, parent, key, label):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=4)

        ttk.Label(frame, text=label, width=20).pack(side="left")

        color_value = self.palette.get(key, "#000000")
        btn = tk.Button(
            frame,
            bg=color_value,
            width=10,
            command=lambda k=key: self._pick_color(k),
        )
        btn.pack(side="left", padx=4)
        self.color_buttons[key] = btn

        value_label = ttk.Label(frame, text=color_value, font=("Courier", 9))
        value_label.pack(side="left", fill="x", expand=True)

    def _pick_color(self, key):
        current = self.palette.get(key, "#000000")
        color = colorchooser.askcolor(color=current, title=f"Pick color for {key}")
        if color[1]:  # color[1] is the hex string
            self.palette[key] = color[1]
            self.color_buttons[key].configure(bg=color[1])
            # Update the label next to it
            parent = self.color_buttons[key].master
            for widget in parent.winfo_children():
                if isinstance(widget, ttk.Label) and widget != parent.winfo_children()[0]:
                    widget.configure(text=color[1])
                    break

    def _reset(self):
        if not messagebox.askyesno("Reset", "Reset to current theme colors?"):
            return
        self.palette = theme.PALETTE.copy()
        for key, _ in PALETTE_FIELDS:
            color = self.palette[key]
            self.color_buttons[key].configure(bg=color)

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Save", "Please enter a theme name.")
            return
        if self.theme_manager.is_builtin(name) and name != self.theme_name:
            messagebox.showerror(
                "Save",
                f"Cannot save as '{name}' (builtin theme). Choose a different name.",
            )
            return
        if not self.theme_manager.save_theme(name, self.palette):
            messagebox.showerror("Save", "Failed to save theme.")
            return
        messagebox.showinfo("Save", f"Theme '{name}' saved successfully.")
        self.destroy()