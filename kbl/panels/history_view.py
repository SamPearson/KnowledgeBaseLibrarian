"""History view: conversation rendering, thinking collapse, tool output."""

import json
import re
import tkinter as tk

try:
    import ttkbootstrap as ttk
except ImportError:
    from tkinter import ttk

from kbl import markdown_render, theme

_TOOL_PREVIEW_LIMIT = 160


class HistoryView:
    def __init__(self, master, on_edit, on_delete, stop_progress):
        self.widget = tk.Text(master, wrap="word", state="disabled")
        theme.style_text(self.widget)
        self.widget.bind("<Configure>", lambda e: self.resize_dividers())

        self._on_edit = on_edit
        self._on_delete = on_delete
        self._stop_progress = stop_progress

        self._message_blocks = []
        self._message_buttons = []
        self._content_start_mark = None
        self._msg_seq = 0
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._thought_blocks = []
        self._thought_seq = 0
        self._dividers = []

    # ---- styling ----

    def restyle(self):
        theme.style_text(self.widget)
        markdown_render.setup_md_tags(self.widget)
        self.widget.tag_configure(
            "who",
            foreground=theme.PALETTE["accent"],
            font=(theme.FAMILY, theme.SIZE, "bold"),
        )
        self.widget.tag_configure(
            "who_assistant",
            foreground=theme.PALETTE["accent_hover"],
            font=(theme.FAMILY, theme.SIZE, "bold"),
        )
        self.widget.tag_configure(
            "think",
            foreground=theme.PALETTE.get(
                "chrome_text_dim", theme.PALETTE["chrome_text"]
            ),
            font=(theme.FAMILY, theme.SIZE, "italic"),
        )
        self.widget.tag_configure(
            "tool",
            foreground=theme.PALETTE.get("accent", theme.PALETTE["chrome_text"]),
            font=(theme.MONO_FAMILY, theme.SIZE),
        )
        self.widget.tag_configure(
            "tool_res",
            foreground=theme.PALETTE.get(
                "chrome_text_dim", theme.PALETTE["chrome_text"]
            ),
            font=(theme.MONO_FAMILY, theme.SIZE - 1),
        )
        for _sep in self._dividers:
            _sep.configure(bg=theme.PALETTE["border"])

    # ---- streaming ----

    def reset_stream_state(self):
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._content_start_mark = None

    def start_stream(self):
        self.widget.configure(state="normal")
        self._maybe_divider()
        self.widget.insert("end", "\nAssistant:\n", "who_assistant")
        self.widget.configure(state="disabled")

    def append_thinking(self, piece):
        self._stop_progress()
        if self._thinking_start is None:
            self._thinking_start = self.widget.index("end-1c")
        self._thinking_text.append(piece)
        self.widget.configure(state="normal")
        self.widget.insert("end", piece, "think")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def append_stream(self, piece):
        self._stop_progress()
        if not self._thinking_collapsed and self._thinking_text:
            self._collapse_thinking()
        self.widget.configure(state="normal")
        if self._content_start_mark is None:
            self._msg_seq += 1
            self._content_start_mark = f"_a{self._msg_seq}_s"
            self.widget.mark_set(self._content_start_mark, "end-1c")
            self.widget.mark_gravity(self._content_start_mark, "left")
        self.widget.insert("end", piece)
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def _collapse_thinking(self):
        self._thinking_collapsed = True
        self._stop_progress()
        thinking = "".join(self._thinking_text)
        if not thinking:
            return
        seq = self._thought_seq
        self._thought_seq += 1
        anchor = self._thinking_start
        toggle = ttk.Button(self.widget, text=f"Thought process \u25b8{seq}")
        toggle.configure(command=lambda b=seq: self.toggle_thought(b))
        self._thought_blocks.append(
            {
                "seq": seq,
                "button": toggle,
                "text": thinking,
                "mark": f"_thought{seq}",
                "shown": False,
            }
        )
        self.widget.configure(state="normal")
        self.widget.delete(anchor, "end")
        self.widget.window_create(anchor, window=toggle)
        self.widget.mark_set(f"_thought{seq}", f"{anchor} + 1c")
        self.widget.mark_gravity(f"_thought{seq}", "left")
        self.widget.configure(state="disabled")

    def toggle_thought(self, seq):
        block = next(b for b in self._thought_blocks if b["seq"] == seq)
        insert_at = self.widget.index(block["mark"])
        self.widget.configure(state="normal")
        if block["shown"]:
            end = self.widget.index(f"{insert_at} + {len(block['text'])}c")
            self.widget.delete(insert_at, end)
            block["shown"] = False
            block["button"].configure(text=f"Thought process \u25b8{seq}")
        else:
            self.widget.insert(insert_at, block["text"], "think")
            block["shown"] = True
            block["button"].configure(text=f"Thought process \u25be{seq}")
        self.widget.see(insert_at)
        self.widget.configure(state="disabled")

    def finish(self, conversation):
        self.widget.configure(state="normal")
        if (
            self._content_start_mark is not None
            and conversation
            and conversation[-1].get("role") == "assistant"
            and conversation[-1].get("content")
        ):
            end_mark = f"_a{self._msg_seq}_e"
            self.widget.mark_set(end_mark, "end-1c")
            self.widget.mark_gravity(end_mark, "left")
            start = self.widget.index(self._content_start_mark)
            end = self.widget.index(f"{end_mark} + 1c")
            body = self.widget.get(start, end)
            self.widget.delete(start, end)
            markdown_render.append_md(self.widget, body)
            self.widget.mark_set(end_mark, "end-1c")
            self.widget.mark_gravity(end_mark, "left")
            self._message_blocks.append(
                {
                    "role": "assistant",
                    "conv_index": len(conversation) - 1,
                    "start_mark": self._content_start_mark,
                    "end_mark": end_mark,
                }
            )
            self._add_edit_footer(len(conversation) - 1, "assistant")
        self.widget.insert("end", "\n")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    # ---- history helpers ----

    def append(self, who, text, conv_index=None):
        self.widget.configure(state="normal")
        self._maybe_divider()
        self.widget.insert("end", "\n")
        if who:
            self.widget.insert("end", f"{who}: ", "who")
        start = self.widget.index("end-1c")
        if text:
            if who == "User":
                markdown_render.append_md(self.widget, text)
            else:
                self.widget.insert("end", text)
        end = self.widget.index("end-1c")
        if who == "User" and text:
            self._msg_seq += 1
            start_mark = f"_m{self._msg_seq}_s"
            end_mark = f"_m{self._msg_seq}_e"
            self.widget.mark_set(start_mark, start)
            self.widget.mark_gravity(start_mark, "left")
            self.widget.mark_set(end_mark, end)
            self.widget.mark_gravity(end_mark, "left")
            ci = conv_index if conv_index is not None else 0
            self._message_blocks.append(
                {
                    "role": "user",
                    "conv_index": ci,
                    "start_mark": start_mark,
                    "end_mark": end_mark,
                }
            )
            self._add_edit_footer(ci, "user")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    # ---- message dividers ----

    def _maybe_divider(self):
        if self.widget.compare("end-1c", ">", "1.0"):
            self._insert_divider()

    def _insert_divider(self):
        sep = tk.Frame(self.widget, height=1, relief="flat", bd=0)
        sep.configure(bg=theme.PALETTE["border"])
        self.widget.window_create("end", window=sep, pady=6)
        self._dividers.append(sep)
        self.resize_dividers()

    def resize_dividers(self):
        width = self.widget.winfo_width() - 32
        if width < 1:
            return
        for sep in self._dividers:
            sep.configure(width=width)

    # ---- message editing ----

    def _add_edit_footer(self, conv_index, role):
        footer = ttk.Frame(self.widget)
        ttk.Button(
            footer,
            text="Edit",
            takefocus=0,
            command=lambda ci=conv_index, r=role: self._on_edit(ci, r),
        ).pack(side="left", padx=(0, 4))
        ttk.Button(
            footer,
            text="Delete",
            takefocus=0,
            command=lambda ci=conv_index: self._on_delete(ci),
        ).pack(side="left")
        self.widget.window_create("end", window=footer)
        self.widget.insert("end", "\n")
        self._message_buttons.append(footer)

    # ---- full render ----

    def clear(self):
        self.widget.configure(state="normal")
        for btn in self._message_buttons:
            btn.destroy()
        self._message_buttons = []
        self.widget.delete("1.0", "end")
        self.widget.configure(state="disabled")
        self._message_blocks = []
        self._thought_blocks = []
        self._dividers = []
        self._thinking_text = []
        self._thinking_start = None
        self._thinking_collapsed = False
        self._content_start_mark = None
        self._msg_seq = 0
        self._thought_seq = 0

    def render_history(self, conversation):
        self.clear()
        for index, message in enumerate(conversation):
            role = message.get("role")
            content = message.get("content")
            if role == "user":
                match = re.match(r"^\[Attached file: ([^\]]+)\]", content or "")
                if match:
                    self.append("Attached", match.group(1))
                elif content:
                    self.append("User", content, index)
            elif role == "assistant" and isinstance(content, str) and content:
                self._render_assistant(index, content)

    def _render_assistant(self, conv_index, content):
        self.widget.configure(state="normal")
        self._maybe_divider()
        self.widget.insert("end", "\nAssistant:\n", "who_assistant")
        start = self.widget.index("end-1c")
        self._msg_seq += 1
        start_mark = f"_a{self._msg_seq}_s"
        self.widget.mark_set(start_mark, start)
        self.widget.mark_gravity(start_mark, "left")
        markdown_render.append_md(self.widget, content)
        end_mark = f"_a{self._msg_seq}_e"
        self.widget.mark_set(end_mark, "end-1c")
        self.widget.mark_gravity(end_mark, "left")
        self._message_blocks.append(
            {
                "role": "assistant",
                "conv_index": conv_index,
                "start_mark": start_mark,
                "end_mark": end_mark,
            }
        )
        self._add_edit_footer(conv_index, "assistant")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    # ---- tool call rendering ----

    def render_tool_call(self, call):
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
        self.widget.configure(state="normal")
        self.widget.insert("end", f"\n  \u2192 {name}({shown})", "tool")
        self.widget.see("end")
        self.widget.configure(state="disabled")

    def render_tool_result(self, call_result):
        _call, result = call_result
        preview = " ".join((result or "").split())
        if len(preview) > _TOOL_PREVIEW_LIMIT:
            preview = preview[:_TOOL_PREVIEW_LIMIT] + "\u2026"
        if not preview:
            return
        self.widget.configure(state="normal")
        self.widget.insert("end", f"\n    {preview}", "tool_res")
        self.widget.see("end")
        self.widget.configure(state="disabled")