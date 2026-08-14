# M4 — Tool Management

## Goal

Turn tools into real, user-managed objects. A manager UI, folder-based storage,
and enable/disable — built-ins and user tools all behind the M3 interface.
M4 is "turn on the folder scan"; the M3 contract doesn't change.

## Where tools live

Three sources, one interface (`{name, description, parameters, callable}`):

- **Built-ins** — ship in app code (the M3 catalog).
- **Global tools** — a user-writable root, available in every workspace.
- **Workspace tools** — a root inside the workspace, only for that workspace.

Each user tool is a folder in the OpenClaw-skill style:

```
<tools_root>/<name>/
  SKILL.md   # frontmatter: name + description; body: when/how to use it
  tools.py   # optional: functions, each registering a name, description, schema
```

- At startup, scan all three roots, parse each `SKILL.md`, and inject the
  name/description into the system prompt so the model knows what exists and
  when to use it (gating).
- Import each `tools.py`, collect its tools, and register the schemas alongside
  the built-ins.
- Tool folders are excluded from the wiki's `list_files`, so they don't pollute
  the wiki context.

## Tool manager UI

Built on the existing file tree and editor:

- The manager lists all tools, grouped by source (built-ins / global /
  workspace).
- Selecting a tool opens its `SKILL.md` in the existing editor; `tools.py`
  is editable the same way.
- Creating a tool = adding a folder under the global or workspace root.
- Renaming/deleting a tool = file operations in the tree.

## Enable / disable

- Config holds an enabled-tools list, and it covers built-ins too — if the user
  wants to disable core tools, that's on them.
- Disabled tools don't appear in the prompt or schemas.
- This is the on/off switch for the narrow-AI guarantee.

## Sample tool

- Ship one sample workspace tool (e.g. a small todo API backed by a JSON file)
  that demonstrates `SKILL.md` + `tools.py` end to end.

## Safety

- Tools are arbitrary local Python in the app process: same trust model as any
  installed app code. Users should only install tools they trust.

## Acceptance criteria

- Dropping a tool folder into the global or workspace root and restarting
  exposes its tools to the model.
- Skill descriptions steer the model to use the right tool for the right ask.
- Built-ins (wiki, date, search) keep working through the same interface.
- The manager UI can create/edit/delete tools via the tree and editor.
- Disabled tools (built-ins included) don't appear in the prompt or schemas.
- Workspace tools are only available in their own workspace.
- The sample todo tool answers a question that reads/writes its store.