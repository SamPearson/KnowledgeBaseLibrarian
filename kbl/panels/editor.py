"""Editor panel: edit mode (Text) and display mode (rendered markdown)."""

import tkinter as tk
from pathlib import Path

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import markdown_render, theme


class EditorPanel(ttk.Frame):
    def __init__(self, master, config):
        super().__init__(master)
        self.config = config
        self.file_path = None
        self.mode = "edit"
        self._dirty = False

        self._build_toolbar()
        self._build_body()

    def _build_toolbar(self):
        bar = ttk.Frame(self)
        bar.pack(side="top", fill="x")
        self.title_label = ttk.Label(bar, text="No file", anchor="w", style="Dim.TLabel")
        self.title_label.pack(side="left", fill="x", expand=True, padx=4)
        self.save_button = ttk.Button(
            bar, text="Save", command=self.save, width=6, state="disabled"
        )
        self.save_button.pack(side="right", padx=4, pady=2)
        self.mode_button = ttk.Button(
            bar, text="Display", command=self.toggle_mode, width=8
        )
        self.mode_button.pack(side="right", padx=4, pady=2)

    def _build_body(self):
        body = ttk.Frame(self)
        body.pack(side="top", fill="both", expand=True)

        self.edit_frame = ttk.Frame(body)
        self.text = tk.Text(self.edit_frame, wrap="word", undo=True)
        theme.style_text(self.text)
        scroll = ttk.Scrollbar(
            self.edit_frame, orient="vertical", command=self.text.yview
        )
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.display_frame = ttk.Frame(body)
        self._fallback_text = None

        self._show_edit()

        self.text.bind("<Control-s>", lambda e: (self.save(), "break"))
        self.text.bind("<Control-e>", lambda e: (self.toggle_mode(), "break"))
        self.text.bind("<<Modified>>", self._on_modified)

    def _show_edit(self):
        self.display_frame.pack_forget()
        self.edit_frame.pack(fill="both", expand=True)

    def _show_display(self):
        self.edit_frame.pack_forget()
        if self._fallback_text is None:
            self._fallback_text = tk.Text(
                self.display_frame, wrap="none", state="disabled"
            )
            theme.style_text(self._fallback_text)
            v_scroll = ttk.Scrollbar(
                self.display_frame, orient="vertical",
                command=self._fallback_text.yview,
            )
            self._fallback_text.configure(yscrollcommand=v_scroll.set)
            h_scroll = ttk.Scrollbar(
                self.display_frame, orient="horizontal",
                command=self._fallback_text.xview,
            )
            self._fallback_text.configure(xscrollcommand=h_scroll.set)
            self._fallback_text.pack(side="left", fill="both", expand=True)
            v_scroll.pack(side="right", fill="y")
            h_scroll.pack(side="bottom", fill="x")
        self.display_frame.pack(fill="both", expand=True)
        self._refresh_display()

    def _refresh_display(self):
        content = self.text.get("1.0", "end-1c")
        if self._fallback_text is not None:
            markdown_render.render_md_in_text(self._fallback_text, content)

    def _on_modified(self, _event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._set_dirty(True)

    def toggle_mode(self):
        if self.mode == "edit":
            self.mode = "display"
            self._show_display()
            self.mode_button.config(text="Edit")
        else:
            self.mode = "edit"
            self._show_edit()
            self.mode_button.config(text="Display")

    def open(self, path):
        self.file_path = Path(path)
        try:
            content = self.file_path.read_text(encoding="utf-8")
        except OSError:
            content = ""
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_modified(False)
        self._set_dirty(False)
        self._update_title()
        if self.mode == "display":
            self._refresh_display()

    def save(self):
        if self.file_path is None:
            return
        content = self.text.get("1.0", "end-1c")
        try:
            self.file_path.write_text(content, encoding="utf-8")
        except OSError as exc:
            tk.messagebox.showerror("Save", f"Could not save file: {exc}")
            return
        self.text.edit_modified(False)
        self._set_dirty(False)

    def _set_dirty(self, dirty):
        self._dirty = dirty
        self.save_button.config(state="normal" if dirty else "disabled")
        self._update_title()

    def _update_title(self):
        name = self.file_path.name if self.file_path else "No file"
        marker = "*" if self._dirty else ""
        self.title_label.config(text=f"{marker}{name}")

    def _restyle(self):
        """Re-apply theme styling."""
        theme.style_text(self.text)
        if self._fallback_text is not None:
            theme.style_text(self._fallback_text)
            self._refresh_display()