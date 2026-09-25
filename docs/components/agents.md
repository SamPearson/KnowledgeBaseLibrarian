# agents

## Purpose
Agent identities: one directory per agent under `~/.kbl/agents`, each with a `system_prompt.md` (sent as the system message every turn) and an optional `agent.json` metadata file (M4) carrying role, parent, enabled tools, and delegation limits. Users create, edit, delete, and switch agents at any time.

## Location
`kbl/agents.py`.

## Inputs
- Agent name, prompt text, optional metadata dict.
- Filesystem at `AGENTS_DIR = CONFIG_DIR / "agents"`.

## Outputs
- `list_agents()` -> names; `system_prompt(name)` / prompt saving; agent CRUD (create/rename/delete/copy); `agent.json` read/write.
- Constants: `PROMPT_FILE="system_prompt.md"`, `METADATA_FILE="agent.json"`, `DEFAULT_AGENT="assistant"`, `DEFAULT_MAX_TURNS=8`, `DEFAULT_MAX_DEPTH=1`.
- Raises `AgentError` on invalid names (regex `^[A-Za-z0-9][A-Za-z0-9 _-]*$`) or storage problems.

## Dependencies
- `kbl.config` (`CONFIG_DIR`). stdlib `json`, `shutil`, `re`.

## Events
None (pure module; UI maps `agent_changed` to its own state).

## Contracts it satisfies
- None from `~kbl.contracts`; supplies agent metadata consumed by `harness` (system prompt, `max_turns`, `max_depth`, tool allowlist) and by `agent_manager` dialog.

## Subagents
Gives delegation its limits: the child agent's `max_turns` is reserved against `max_delegated_turns`, and `max_depth` bounds recursion. An agent without `agent.json` may not delegate (no parent/role).

## Isolation
Pure service — no Tkinter import (guarded by `tests/test_purity.py`), deterministic given a `CONFIG_DIR`.

## Testability
Strong: `tests/test_agents.py` exercises CRUD and validation against a temp `CONFIG_DIR` without a display.

## Fork implications
- Adding agent attributes (avatar, temperature, tools) means extending `agent.json` + the manager dialog; backward compatible because metadata is optional.
- Prompt templating or per-agent model overrides layer cleanly onto the same directory-per-agent model.