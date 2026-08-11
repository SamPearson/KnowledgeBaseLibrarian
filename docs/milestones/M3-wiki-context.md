# M3 — Wiki Context

## Goal

The model can read the wiki. The flagship question — "what's tomorrow's
workout look like" — works using only built-in tools and the md files.

## Built-in tools

All behind the same "name + description + callable" interface defined in
design.md (this is what M4 plugs into).

- `list_files` — list the wiki's md files/folders.
- `read_file(path)` — return a file's contents.
- `get_current_date` — current date/time, so the model can resolve "tomorrow".

## Function calling with Ollama

- `/api/chat` with a `tools` list. Requires a tool-supporting model
  (e.g. qwen2.5 / llama3.1+); picking the model happens in M2's dialog.
- Chat loop:
  1. Build request: system prompt + conversation + tool schemas.
  2. If the response contains a tool call, run the Python function.
  3. Append the result as a tool message, repeat from step 1.
  4. Otherwise, render the reply.
- Tool execution is just calling a Python function and feeding the result back.

## System prompt

- Minimal and narrow on purpose:
  - You're an assistant living in the user's markdown wiki.
  - You can list/read wiki files and get the current date.
  - Prefer reading files over guessing. Keep answers short.

## Threading

- The whole loop runs in a background thread; it posts events to the UI.
- One conversation turn at a time (matches M2's single-request rule).

## Acceptance criteria

- "What's tomorrow's workout look like" is answered from wiki files, resolving
  dates correctly via the date tool.
- The model reads files rather than inventing contents.
- A turn involving several file reads completes and renders normally.
