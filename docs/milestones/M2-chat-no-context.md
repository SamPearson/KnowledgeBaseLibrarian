# M2 — Chat, No Context

## Goal

The chat panel comes alive: pick a model, send messages, stream replies. No
wiki context yet — just a conversation. This is where we learn the Ollama
client and prompting.

## Model provider config

- Dialog: Ollama host (default `http://localhost:11434`) and model name.
  Model list can be fetched from `/api/tags` for a dropdown; allow manual entry.
- Stored in the config JSON from M1.

## Ollama client

- Direct HTTP to `/api/chat` (keeps dependencies light) or the `ollama`
  package; pick whichever is less fuss.
- Stream responses; update the chat incrementally as tokens arrive.

## Chat panel

- History as a read-only `Text` widget, input box, send button, stop button.
- Run the request in a background thread so the UI stays responsive. One
  in-flight request at a time; send is disabled while generating.
- Conversation history kept in memory for the session; clear button.

## Out of scope

- Tools, wiki access, and any system prompt beyond a minimal identity line.

## Acceptance criteria

- Configure a model from the dialog.
- Send a message and see a streamed reply appear in the panel.
- Stop a long reply mid-stream.
- Chat works with the app's other panels open.
