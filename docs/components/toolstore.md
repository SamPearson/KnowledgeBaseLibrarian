# toolstore

## Purpose
Tool discovery and management over three sources unified behind one `{name, description, parameters, callable}` interface: built-ins (shipped in `kbl.tools`), global tools under `~/.kbl/tools`, and workspace tools under a workspace's `tools/` folder.

## Location
`kbl/toolstore.py`.

## Inputs
- `builtins()` (from `kbl.tools` M3 catalog), root paths for global/workspace tools, config `disabled_tools`.

## Outputs
- `list_tools(workspace=None)` merged + filtered (disabled omitted from schemas and system prompt); tool execution dispatch; user-tool CRUD (create/rename/delete).

## User tool layout
```
<tools_root>/<name>/
  SKILL.md   # frontmatter name+description; body documents usage
  tools.py   # optional: exposes tools() callable or TOOLS list of kbl.tools.Tool
```
Imported dynamically via `importlib.util` on discovery. Constants: `SKILL_FILENAME="SKILL.md"`, `TOOLS_FILENAME="tools.py"`, `TOOLS_ROOT_NAME="tools"`.

## Dependencies
- `kbl.config`, `kbl.tools` (`Tool`). stdlib `importlib.util`, `re`, `shutil`.

## Events
None (pure). The `tool_manager` dialog opens a tool's `SKILL.md` in the editor via `file_opened`.

## Contracts it satisfies
- None directly; tools conform to the `Tool` shape that `harness` injects into the model schema.

## Subagents
Participates in delegation: the request's `tool_allowlist` is intersected with the child agent's `allowed_tools`, and the merged list is what the child sees.

## Isolation
Pure service — no Tkinter (guarded by purity tests), depends only on config + filesystem.

## Testability
Strong: `tests/test_toolstore.py` uses a temp tools root; discovery/disable/source-precedence are covered without a display.

## Fork implications
- A skill-based (OpenClaw-style) tool format already matches; adding a new source is one more root scan.
- Sandboxing/execution policy (subprocess, denylists) would slot between discovery and the `callable` wrapper.