# Application Design

## Overview

Desktop app (Python + tkinter): a markdown editor with an AI chat panel.
See [pitch.md](pitch.md) for the project pitch.

## UI layout

- Launching the application presents a window.
- The user can configure the number, position, and size of panels in the window.
- The window has a file tree manager; you can create and delete md files and
  folders.
- The window has a file editor, which can be in edit or display mode.
- The window has a chat panel (not hooked up to anything yet).

## Workspaces

- A workspace (a.k.a. project) is a top-level folder on disk whose markdown
  files form a knowledge base.
- The user manages a list of workspace paths (add/remove) and one active
  workspace; the file tree mirrors the active workspace's directory.

## Server configuration

- A server configuration dialog. The user enters a single server URL covering
  protocol, host, port, and any path suffix in one field, e.g.
  `http://localhost:11434/v1` (Ollama) or `http://localhost:8080/v1`
  (llama.cpp server).
- Both Ollama and llama.cpp expose the OpenAI-compatible API at `<host>/v1`, so
  one client handles both servers.
- Chat happens in the chat panel. Go as simple as possible first.

## Context strategy

Full files are fed into the LLM. Simplest thing to implement; we can revisit
retrieval/chunking later if file sizes make it impractical.

Two pieces of context the chat always has access to (built-ins):

- The markdown wiki: listing/reading the files in the tree.
- The current date/time (the model needs to know when "tomorrow" is).

## Plugins / Skills

Modeled after OpenClaw skills (AgentSkills spec): a folder containing a `SKILL.md`
with YAML frontmatter (`name`, `description`) and a markdown body of instructions,
optionally bundled with executable code.

### The line that defines a plugin

> A plugin is anything that gathers context or takes action **outside the
> markdown wiki**.

- Wiki knowledge (e.g. "what workout goes on what day") lives in the md files,
  so it's built-in context, not a plugin.
- Reaching an external system (Redmine API, todo API) is a plugin.
- This keeps the default AI surface narrow: just the wiki plus date. Everything
  else is opt-in.

### Contract

```
plugins/<name>/
  SKILL.md   # frontmatter: name + description; body: when/how to use it
  tools.py   # optional: functions, each registering a name, description, schema
```

- At startup the app scans `plugins/`, parses each `SKILL.md`, and injects the
  name/description into the system prompt so the model knows what exists and
  when to use it (this is the "gating").
- Tool schemas = built-ins (wiki file ops, date) + each plugin's `tools.py`,
  exposed to the model as callable functions. Ollama supports function calling
  natively.
- Chat flow: user message -> model -> optional tool call -> app runs the Python
  function -> result fed back -> model continues.

Built-ins are kept behind the same "name + description + callable" interface as
plugins, so a plugin is just "enable the folder scan."

### MVP stance

Implement only built-ins (wiki + date) for the MVP. The plugin system is then
turning on the folder scan later; the contract doesn't change.

### Notes

- Plugins are arbitrary local Python; same trust model as any locally installed
  app code. Users should only install plugins they trust.

## Milestones

Each milestone is a big enough bite to build and use on its own. Nothing ships
until the milestone is usable end-to-end.

Each milestone has a design doc: [M1](milestones/M1-app-shell.md),
[M2](milestones/M2-chat-no-context.md), [M3](milestones/M3-wiki-context.md),
[M4](milestones/M4-plugin-system.md).

### M1 — App shell

- Window with configurable panels (number, position, size).
- File tree manager: add/remove md files.
- File editor with edit and display modes.
- No chat yet.

### M2 — Chat, no context

- Server configuration dialog.
- Chat panel wired up: send messages, see replies.
- No context: the model gets only the conversation.
- Learn the OpenAI-compatible client / prompting here.

### M3 — Wiki context

- Built-in tools: wiki file ops (list/read) and current date/time.
- Wire function calling so the model can pull files as context.
- Goal: "what's tomorrow's workout" works using only the wiki.

### M4 — Plugin system

- Folder scan for `plugins/<name>/SKILL.md`.
- Parse frontmatter, inject name/description into the system prompt.
- Register each plugin's `tools.py` callables as tools.
- Ship with a sample plugin (e.g. a todo API) to prove the contract.
- Built-ins stay on the same interface; this milestone is "turn on the scan."

### Deferred / not planned

- Retrieval/chunking for large wikis (revisit only if full-file injection breaks).
- Anything beyond reading/writing the wiki and plugin-provided tools.
