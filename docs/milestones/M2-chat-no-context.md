# M2 — Chat, No Context

## Goal

The chat panel comes alive: pick a model, send messages, stream replies. No
wiki context yet — just a conversation. This is where we learn the
OpenAI-compatible client and prompting.

## Server configuration

- Dialog: a single server URL field covering protocol, host, port, and any path
  suffix — e.g. `http://localhost:11434/v1` (Ollama) or
  `http://localhost:8080/v1` (llama.cpp server). Optional API key field for
  servers that want one.
- Both Ollama and llama.cpp expose the OpenAI-compatible API at `<host>/v1`, so
  one client handles both.
- Model list fetched from `/v1/models` for a dropdown; allow manual entry.
- Stored in the config JSON from M1.

## Chat client

- OpenAI-compatible chat completions at `<server>/chat/completions`.
- Use the `openai` package pointed at the user's server URL as the base URL;
  pick the least fuss option.
- Stream responses; update the chat incrementally as tokens arrive.

## Chat panel

- History as a read-only `Text` widget, input box, send button, stop button.
- Run the request in a background thread so the UI stays responsive. One
  in-flight request at a time; send is disabled while generating.
- Conversation history kept in memory for the session; clear button.

## Thinking / reasoning stream

- Models with a thinking phase (e.g. Qwen3 on Ollama) emit `reasoning` deltas
  before the answer; stream them into the panel in a dim secondary style.
- While the server is still preparing (before the first token arrives), show an
  indeterminate progress indicator.
- When the real answer starts, collapse the thinking into an expandable
  "Thought process" toggle. Expanding restores the thinking in the panel;
  only the answer text is saved to the conversation.

## Agents (system prompts)

- The identity line is customizable per "agent": each agent is a directory
  `~/.kbl/agents/<name>/system_prompt.md` containing its system prompt.
- The active agent's system prompt is sent with every message.
- Create, rename, delete, edit, and switch agents from an Agents dialog and a
  toolbar/menu selector.
- A default `assistant` agent is seeded on first run.

## Out of scope

- Tools, wiki access, and any system prompt beyond the agent identity line.

## Acceptance criteria

- Configure a server and model from the dialog.
- Send a message and see a streamed reply appear in the panel.
- Stop a long reply mid-stream.
- Chat works with the app's other panels open.