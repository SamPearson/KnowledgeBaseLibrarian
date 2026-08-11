# M4 — Plugin System

## Goal

Turn on the folder scan described in design.md. Skills and their tools become
real, on top of the built-in interface that M3 established.

## Discovery

- At startup, scan `plugins/` for `plugins/<name>/SKILL.md`.
- Parse frontmatter (`name`, `description`) and keep the body as instructions.
- Import each plugin's `tools.py` and collect its tools.
- Inject each skill's name + description into the system prompt so the model
  knows it exists and when to use it (gating).
- Register all tool schemas with Ollama alongside the built-ins.

## `tools.py` contract

- The plugin exposes a `tools()` function returning a list of
  `{name, description, parameters, func}` dicts.
- Provide a small app helper (`@tool(...)` decorator) so plugins can be
  declarative instead of hand-building dicts.
- Tool bodies run in the app process (like M3 built-ins) — no subprocesses.

## Enable / disable

- Config holds an enabled-plugins list; disabled plugins are skipped at scan.
- This is the on/off switch for the "narrow AI" guarantee.

## Sample plugin

- Ship one sample plugin (e.g. a small todo API backed by a JSON file) that
  demonstrates `SKILL.md` + `tools.py` end to end.

## Safety

- Plugins are arbitrary local Python in the app process: same trust model as
  any installed app code. Users should only install plugins they trust.

## Acceptance criteria

- Dropping a plugin folder into `plugins/` and restarting exposes its tools to
  the model.
- Skill descriptions steer the model to use the right plugin for the right ask.
- Built-ins (wiki, date) keep working through the same interface.
- Disabled plugins don't appear in the prompt or schemas.
- The sample todo plugin answers a question that reads/writes its store.
