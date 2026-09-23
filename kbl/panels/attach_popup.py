"""@-mention file suggestion popup for the chat input widget."""

import tkinter as tk

from kbl import theme, tools

_SUGGESTION_LIMIT = 30


class AttachPopup:
    """Lives for one streaming turn. Renders a file suggestion popup.

    Reads the token after the last ``@`` in the current input line and offers
    matching files from the active workspace. Caller binds input events to
    :meth:`maybe_show`, :meth:`down`, :meth:`up`, :meth:`close`.
    """

    def __init__(self, input_widget, get_workspace, is_streaming):
        self.input = input_widget
        self._get_workspace = get_workspace
        self._is_streaming = is_streaming
        self._popup = None
        self._list = None
        self._token_start = None
        self._binding = None

    @property
    def active(self):
        return self._popup is not None

    def _token(self):
        insert = self.input.index("insert")
        line = insert.split(".")[0]
        line_text = self.input.get(f"{line}.0", "insert")
        idx = line_text.rfind("@")
        if idx < 0:
            return None, None, None
        return line_text[idx + 1 :], f"{line}.{idx}", insert

    def maybe_show(self, event=None):
        if self._is_streaming():
            self.close()
            return
        workspace = self._get_workspace()
        if not workspace:
            self.close()
            return
        token, start, _insert = self._token()
        if token is None or " " in token:
            self.close()
            return
        try:
            files = tools.list_md_files(workspace)
        except Exception:
            self.close()
            return
        lower = token.lower()
        items = [
            f for f in files if f.lower().startswith(lower)
        ][:_SUGGESTION_LIMIT]
        if not items:
            self.close()
            return
        self._show(items, start)

    def _show(self, items, token_start):
        self.close()
        top = tk.Toplevel(self.input)
        top.withdraw()
        top.overrideredirect(True)
        listbox = tk.Listbox(
            top,
            exportselection=False,
            activestyle="dotbox",
            height=min(len(items), 8),
            width=max((len(i) for i in items), default=20) + 2,
        )
        listbox.pack(fill="both", expand=True)
        for item in items:
            listbox.insert("end", item)
        theme.style_listbox(listbox)
        listbox.selection_set(0)
        listbox.activate(0)
        listbox.bind("<ButtonRelease-1>", lambda e: self.complete())
        listbox.bind("<Double-Button-1>", lambda e: self.complete())
        self._popup = top
        self._list = listbox
        self._token_start = token_start
        self._binding = self.input.bind_all("<Button-1>", self._on_popup_click)
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
        if self._popup is None:
            return
        widget = event.widget
        while widget is not None:
            if widget is self._popup:
                return
            widget = widget.master
        self.close()

    def complete(self):
        if self._popup is None:
            return
        selection = self._list.curselection()
        if not selection:
            self.close()
            return
        path = self._list.get(selection[0])
        start = self._token_start
        self.input.delete(start, "insert")
        self.input.insert(start, path)
        self.close()

    def close(self, _event=None):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except tk.TclError:
                pass
        if self._binding is not None:
            try:
                self.input.unbind_all(self._binding)
            except tk.TclError:
                pass
        self._popup = None
        self._list = None
        self._token_start = None
        self._binding = None

    def down(self, _event=None):
        if self._popup is None:
            return None
        listbox = self._list
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        if index < listbox.size() - 1:
            listbox.selection_clear(0, "end")
            listbox.selection_set(index + 1)
            listbox.activate(index + 1)
            listbox.see(index + 1)
        return "break"

    def up(self, _event=None):
        if self._popup is None:
            return None
        listbox = self._list
        selection = listbox.curselection()
        index = selection[0] if selection else 0
        if index > 0:
            listbox.selection_clear(0, "end")
            listbox.selection_set(index - 1)
            listbox.activate(index - 1)
            listbox.see(index - 1)
        return "break"