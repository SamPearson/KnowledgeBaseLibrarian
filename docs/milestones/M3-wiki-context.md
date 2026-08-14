# M3 — Wiki Tools & Context

## Goal

The model can read the wiki. The flagship question — "what's tomorrow's workout
look like" — works using only built-in tools and the md files. This milestone
wires the request-composition pipeline (the "two pipes") that M4 plugs into.

## The two pipes

Every chat request has two independent parts, and M3 wires both:

1. **System message** — prose: identity, behavior, what exists, when to use it.
2. **Tools** — a `tools` list of schemas (`{name, description, parameters}`),
   sent alongside the messages.

Between them, three things reach the model:

- **Composed system prose** — agent identity + workspace instructions + tool gating.
- **User-attached files** — files pinned with `@`; injected as messages with
  their contents, sent regardless of what the model decides.
- **Tool results** — `role: "tool"` messages appended when the model calls a tool.

## Built-in tools

All behind the same interface: `{name, description, parameters, callable}`.
"Built-in" just means *ships with the app* — built-ins are editable and
toggleable like any other tool (see M4). The narrow-AI guarantee is: whatever
is enabled is all the model can reach.

Catalog:

- `list_files` — list the wiki's md files/folders.
- `read_file(path)` — return a file's contents.
- `search_files(query)` — grep-style keyword search across the workspace.
- `get_headings(path)` — a file's headings, for cheap relevance checks.
- `get_current_date` — current date/time, so the model can resolve "tomorrow".

Relevance is a loop the model composes: `list_files`/`search_files` to narrow,
`get_headings` to check, `read_file` to pull what matters. Search is deliberately
a set of cheap primitives instead of one opaque "search" tool.

## Function calling

- `/api/chat` with a `tools` list. Requires a tool-supporting model
  (e.g. qwen2.5 / llama3.1+); picking the model happens in M2's dialog.
- Chat loop:
  1. Build request: system message + conversation + tool schemas.
  2. If the response contains tool calls, run the Python functions.
  3. Append the results as `tool` messages, repeat from step 1.
  4. Otherwise, render the reply.
- Cap the loop (e.g. 8 iterations) so a looping model can't hang a turn.
- Tool execution is just calling a Python function and feeding the result back.

## Tool calls are visible

The M2 client (`kbl/chat_client.py`, `chat_stream`) currently yields only
`("reasoning"|"content")` deltas and drops `delta.tool_calls`. M3 extends it to
accumulate tool-call chunks and stream them; the chat panel renders tool calls
explicitly as they happen. Debuggability is the point: the user should always
see what the model did (`read_file("workout.md")`) even before the final answer.

## System prompt composition

- The system message is assembled per request:
  `agent prompt + workspace instructions + tool gating lines`.
- The **agent** (M2's `~/.kbl/agents/<name>/system_prompt.md`) owns *behavior*:
  tone, persona, how to answer.
- The **workspace** owns *domain*: different workspaces are different wikis, so
  each has its own instruction text ("this is a workout wiki — files are per
  day") steering which tools matter. The tool schemas stay the same.
- Tool gating lines are appended last (see M4 for how user tools contribute).

## User-attached files (@)

- Typing `@` in the chat input shows filename suggestions from the active
  workspace's tree; click or Enter selects.
- Selected files are injected as user-attached context (file contents in the
  request) and are sent regardless of model tool calls.
- Distinct from tools: tools are discovered by the model and invoked at its
  discretion; @-mentions are explicit user context.

## Threading

- The whole loop runs in a background thread; it posts events to the UI.
- One conversation turn at a time (matches M2's single-request rule).

## Acceptance criteria

- "What's tomorrow's workout look like" is answered from wiki files, resolving
  dates correctly via `get_current_date`.
- The model reads files rather than inventing contents.
- A turn involving several file reads completes and renders normally.
- Tool calls are visible in the chat panel as they happen.
- `@`-mentioning a file includes its contents in the request.
