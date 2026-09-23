# M4 — Agent model (Agent/Subagent metadata, opt-in delegation)

Status: **complete** (2026-09-23)

## Goal

Grow `kbl/agents.py` from flat personas (a `system_prompt.md` per directory)
to structured metadata — `description`, `role`, `allowed_tools`, `parent`,
`can_delegate_to`, `max_turns`, `max_depth` — without breaking any existing
`~/.kbl/agents/<name>/system_prompt.md` setup.

## What changed

- **`kbl/contracts.py`** — `Agent` protocol (`id`, `prompt_path` +
  optional `description`/`role`/`allowed_tools` (None = every enabled tool,
  else an allowlist) / `parent` / `can_delegate_to` / `max_turns` /
  `max_depth`) and `AgentRegistry` protocol (`list_agents`, `get`, `active`,
  `can_delegate_to`). (Forward-declared in M2; given concrete shape here.)
- **`kbl/agents.py`**:
  - `@dataclass Agent` — the standing M4 implementation, defaults derived
    from `DEFAULT_MAX_TURNS = 8`, `DEFAULT_MAX_DEPTH = 1`.
  - **Backward-compatible metadata**: optional `agent.json` files live next to
    `system_prompt.md`. `load_agent(name)` treats an absent or corrupt
    `agent.json` as `{}` → every enabled tool allowed, `can_delegate_to=[]`,
    no role/parent. `save_metadata(name, agent)` writes only metadata, never
    touches the prompt file.
  - `AgentRegistry` — lists/loads agents as `Agent` objects, resolves
    `can_delegate_to` transitively (cycle-safe BFS; missing child dirs are
    skipped).
  - Delegation is **opt-in**: default/existing agents have
    `can_delegate_to=[]`, which is the whole point of the milestone — a
    `delegate(...)` tool can never appear for an agent that did not
    explicitly allow it.
- **`kbl/harness.py`** — `build_request` (pre-processing entry used by
  `orchestrate`) now applies the active agent's `allowed_tools` at
  `collect_tools` time: when the allowlist is `None`, every enabled tool is
  passed (identical to before); otherwise the tool list is filtered to the
  allowlist before the system prompt is composed.
- **`kbl/dialogs/agent_manager.py`** — the agent-manager dialog gains a
  "Can delegate to (comma-separated):" entry. Selecting an agent loads its
  current value from `agent.json`; Save persists it via `save_metadata`
  alongside the system prompt. Empty input clears delegation.

## Backward-compatibility guarantee

An agent directory with only `system_prompt.md` and no `agent.json` behaves
exactly as before M4: all enabled tools available, no delegation. Metadata is
purely additive.

## Results

- `pytest tests/test_agents.py` → **27 passed** (10 new M4 tests +
  pre-existing agent storage tests).
- `pytest tests/test_harness.py` → **12 passed** (2 new allowlist tests: a
  restricted agent sees `read_file` but not `list_files`/`search_files` in the
  "## Tools" section; the default agent still gets every tool).
- `pytest tests/` → **166 passed** (154 from M3 + 12 new), headless.
- M4 acceptance:
  - Pre-existing agent dirs (no `agent.json`) behave exactly as before.
  - Delegation is unambiguously opt-in: default agents resolve to
    `can_delegate_to=[]`; `allowed_tools=None` means "all tools", so a
    `delegate(...)` tool can only surface for an explicitly-enabled agent.

## Notes / follow-ups

- The chain-resolution test pins the transitive semantics: a leaf agent
  (`can_delegate_to=[]`) must stay a leaf, or its own targets leak into the
  resolved list.
- Allowlist tests assert only on the `system_prompt.split("## Tools", 1)[1]`
  section, because `DEFAULT_WORKSPACE_INSTRUCTIONS` (kbl/context.py) still
  mentions `list_files` statically even when the tool is filtered out — the
  static mention is cosmetic (the tool list itself is the allowlist), but M5
  could stop special-casing it.
- M5 (delegation orchestrator) builds on this: `Delegator` will read
  `Agent.can_delegate_to`/`allowed_tools` per subagent.