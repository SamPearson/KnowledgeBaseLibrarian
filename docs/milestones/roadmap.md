# Roadmap — Knowledge Base Librarian Framework Migration

A living roadmap that turns `docs/system_architecture.md` from "documented" into "true."
Supersedes the loose milestone ordering in the architecture doc's section 7.

## Locked-in decisions (2026-09-22)

- **Concurrency model:** synchronous + `threading.Event` + free-function `Queue` + `root.after(...)` marshalling. The `Harness`/`StreamEvent` contracts are written **synchronously** (`Iterator[StreamEvent]`, not `AsyncIterator`). No asyncio.
- **Tests are Milestone 0.** Pure-service test suite lands first so the refactors are verifiably non-breaking.
- **"Thin ChatPanel" is its own milestone.** The harness orchestration buried in `kbl/panels/chat.py` (1232 lines) is extracted to the service layer before the EventBus swap.
- **DisplayRenderer contract is in scope** (Milestone 2, with all other contracts). `markdown_render` is the seam the future image-canvas backend plugs into.
- **Delegation stays on the roadmap** (Milestones 5) even though only the D&D system will use it immediately. It is **opt-in per agent** — most agents never delegate.

---

## M0 — Pure-service test suite (foundation)

**Goal:** green baseline proving `tools`, `context`, `conversations`, `config`, `toolstore`, `agents` behave correctly before anything is moved.

Steps:
1. Set up `tests/` + `pytest` (add to requirements / dev extras).
2. `tests/test_tools.py` — `builtin_tools`, `run_tool`, `_within` sandboxing (path escape rejection), `Tool.run`, `ToolError`.
3. `tests/test_context.py` — `compose_system`, `workspace_instructions`, `skill_gating_lines`.
4. `tests/test_conversations.py` — `ConversationStore` round-trips, per-workspace scoping, `workspace_id_for`.
5. `tests/test_config.py` — `Config` load/save/merge, singleton `_DEFAULT_INSTANCE`, migration paths (legacy `active_workspace`, string `active_conversation`), `active_workspace` never persisted.
6. `tests/test_toolstore.py` — scan/collect, disabled-tools gating, skill parsing, sample install.
7. `tests/test_agents.py` — `~/.kbl/agents/<name>/system_prompt.md` layout, list/create/get/set/rename/delete, `active_agent(config)`.
8. Stub contracts document (`docs/milestones/m0-result.md`) recording coverage + any behaviors pinned by tests.

**Acceptance:** `pytest` green with zero GUI (no tkinter import) on everything except render/theme smoke tests. This suite must stay green through M1–M5.

---

## M1 — Thin ChatPanel (extract the harness)

**Goal:** `kbl/panels/chat.py` stops being the orchestrator. Prompt composition + tool loop + streaming assembly move into the service layer. Panel only marshals events.

Steps:
1. New `kbl/harness.py`:
   - `orchestrate(...)` — the current `_stream_worker` body (chat.py:471+): builds messages via `context.compose_system(...)` + `toolstore.collect_tools(...)`, runs the tool round loop capped at `config.max_tool_rounds` (default 8) via `kbl_tools.run_tool`, yields `(kind, payload)` tuples.
   - Synchronous, takes `stop_event: threading.Event`, reads config from an injected `Config`, never touches widgets.
2. Move @-mention attachment read + "attached file" prepending into harness-side message assembly (or a `kbl/messages.py` helper) — panel only passes the raw text + attachment paths.
3. `ChatPanel._start_stream` keeps: spawn thread → `_drain_queue` via `self.after(40, ...)`. The queue now receives harness events instead of the panel assembling them.
4. Delete the prompt/tool-loop code from `chat.py`. Panel keeps rendering (markdown), input capture, suggestions, edit/delete, thinking-collapse buttons.
5. Keep `_refresh_status`/`_refresh_agents` reach-ins for now — they're rework, removed in M3.

**Acceptance:** behavior identical, verified by grep (no `compose_system`/`run_tool`/`collect_tools` imports left in `panels/chat.py`). M0 suite still green.

---

## M2 — contracts.py + DisplayRenderer

**Goal:** the contract surface from architecture-doc section 5 exists, synchronous.

Steps:
1. `kbl/contracts.py` — `Protocol`s (synchronous):
   - `WorkspaceProvider`, `ConfigStore` (document the `Config` singleton as the deliberate implementation), `Device`, `ToolRegistry`, `FileRepository`, `EventBus`, `Harness`, `DisplayRenderer`, `Agent`, `AgentRegistry`, `SubagentRegistry`, `Delegator`, `DelegationRequest`, `DelegationResult`.
   - `Harness` — from architecture doc 4.2 but **sync**: `def send(messages, tools, workspace, stop_event, active_agent=None, parent_task_id=None) -> Iterator[StreamEvent]`.
   - `StreamEvent` typed union: `Content | Reasoning | ToolCall | ToolResult | Done | Error`.
   - `DisplayRenderer`: `setup(widget)`, `render(widget, md_text)`, `append(widget, md_text)`.
2. `kbl/markdown_render.py` (or a thin `MarkdownRenderer` wrapper) declared to satisfy `DisplayRenderer` (`render → render_md_in_text`, `append → append_md`, `setup → setup_md_tags`). No behavior change.
3. Annotate the harness entry point as the sole implementation of `Harness`.

**Acceptance:** `contracts.py` imports cleanly standalone; `markdown_render`/`harness` pass structural `isinstance(renderer, DisplayRenderer)` checks; M0 green.

---

## M3 — EventBus + mediator MainWindow

**Goal:** kill the `self.master` plumbing and cross-panel constructor callbacks.

Steps:
1. `kbl/events.py` — `EventBus` (publish/subscribe, synchronous) + typed payloads from arch-doc 4.1: `WorkspaceSelected`, `FileOpened`, `UserSent`, `AssistantReply`, `ToolRequested`, `ToolResult`, `AgentChanged`, `DelegationRequested`, `SubagentStarted`, `SubagentEvent`, `SubagentCompleted`, `SubagentFailed`.
2. `FileTreePanel` emits `FileOpened(Path)`; no `on_open` callback.
3. `ChatPanel` emits `UserSent`; subscribes to `AssistantReply`/`ToolRequested`/etc. for rendering. Removes `self.master.config` / `self.master.workspaces.active` reads.
4. `MainWindow` becomes a mediator: subscribes bus, drives dialogs, updates panels. Removes per-panel constructor callbacks.
5. Worker-thread → UI marshalling stays `queue` + `root.after`; the bus itself is UI-thread-only, events crossing the thread boundary pass through the queue.

**Acceptance:** grep — no `self.master.` reads remain in `panels/`; `panels/chat.py` under ~800 lines. M0 suites green.

---

## M4 — Agent model (Agent/Subagent metadata, opt-in delegation)

**Goal:** `kbl/agents.py` grows from flat personas to structured metadata without breaking `~/.kbl/agents/<name>/system_prompt.md`.

Steps:
1. `Agent` contract: `id`, `prompt_path`, optional `description`, `role`, `allowed_tools` (None = all toolstore tools, else allowlist), `parent`, `can_delegate_to`, `max_turns`, `max_depth`.
2. Backward-compatible storage: existing agent dirs have no metadata → defaults (no allowlist, `can_delegate_to=[]`). New optional metadata files live alongside `system_prompt.md` (e.g. `~/.kbl/agents/<name>/agent.json`).
3. `AgentRegistry` — list/load by id, resolve `can_delegate_to` chains.
4. Wire `allowed_tools` into `harness.orchestrate` tool loop: apply per-agent allowlist at `collect_tools` time.
5. Default and existing agents remain `can_delegate_to=[]` (opt-in). Agent-manager dialog (optionally) gains a "can delegate to" field.

**Acceptance:** all pre-existing agent dirs behave exactly as today; a delegation-enabled agent is required before `delegate(...)` ever appears in a tool list. M0 green.

---

## M5 — Delegation orchestrator (long-term; D&D driver)

**Goal:** model-driven `delegate(...)` tool call: one subagent, isolated scope, correlated by `task_id`.

Steps:
1. `Delegator` service: on a `delegate(agent_id, task, context)` tool call from a `can_delegate_to` agent, spin a scoped harness invocation (own conversation, own `stop_event`, workspace-scoped, per-agent tool allowlist).
2. Single-level first. `max_depth` enforced; `max_turns` per subagent + total delegated-turn budget cap.
3. `task_id` correlation: `SubagentStarted/SubagentEvent/SubagentCompleted/SubagentFailed` all carry the same `task_id`; cancellation propagates `stop_event` to children.
4. Wire `Delegator` into the `Harness`/orchestrare interface via the synchronous protocol; expose as a tool the LLM can call.

**Acceptance:** a D&D-style scenario (parent agent + 1 child) works end-to-end; parent's tool allowlist does not grant the child any tool the child's own allowlist forbids. M0 green.

---

## M6 — Decoupling seams + per-component docs

**Goal:** make the fork swap a no-code-change operation, then document the decoupled shape. Deliverable #3 from arch-doc section 6.

Steps:
1. **DI seams** — panels take their collaborators via the constructor instead of reaching for modules:
   - `ChatPanel(..., harness=None)` → defaults to the `kbl.harness` module; the `harness.orchestrate(...)` call uses `self._harness`.
   - `HistoryView(..., renderer=None)` + `EditorPanel(..., renderer=None)` → default `MarkdownRenderer()` (already satisfies `DisplayRenderer`); replace `markdown_render.setup_md_tags`/`append_md`/`render_md_in_text` calls with `renderer.setup`/`renderer.append`/`renderer.render`.
   - `MainWindow._build_panels` becomes the single wiring point that passes `harness` and `renderer` instances into the panels.
2. **Write per-component docs** using the template (Purpose/Location/Inputs/Outputs/Dependencies/Events/Contracts/Subagents/Isolation/Testability/Fork implications) for: `MainWindow`, `FileTreePanel`, `EditorPanel` (Display mode), `ChatPanel`, `harness`, `markdown_render`, `EventBus`, `agents`, `toolstore`, each dialog. Docs are written *after* the seams so they describe the final decoupled wiring.
3. **Dead-code sweep**: remove unused `import threading` in `kbl/delegator.py` and the never-referenced `_STOP` in `kbl/chat_client.py`.

**Acceptance:** swapping `harness`→`StableDiffusionHarness` (or `markdown_render`→`ImageRenderer`) requires no edits inside `MainWindow` or `panels/*` — only the wiring point changes. Behavior unchanged; M0 suite green.

---

## M7 — Fork proof

**Goal:** prove the seams with two drop-in swaps.

Status: **complete** — see `m7-result.md`. Two drops landed with zero edits
inside `MainWindow`/`panels/*`, enforced by `tests/test_fork_proof.py`.

Steps:
1. Second harness: a `StableDiffusionHarness` implementing `Harness` (satisfies protocol, plays through the same `EventBus`/`Harness` seams).
2. Second display type: an image-capable display implementing `DisplayRenderer`/`Device` (the fork's `ImageCanvas`). **Planned contract extension:** the current `Device` surface (`cget`/`tag_configure`/`configure`/`delete`/`insert`) and the `StreamEvent` text payloads assume a `Text`-like widget; an image backend needs a narrow extension (a distinct image-renderer protocol and/or an image stream event). Scope this as a mini-plan before M7 work starts.

**Acceptance:** swapping `harness`→`StableDiffusionHarness` (or `markdown_render`→`ImageRenderer`) requires no edits inside `MainWindow` or `panels/*`.

---

## Sequencing rationale

- **M0 first** — refactors are only safe because the pure-services behavior is pinned by tests.
- **M1 before M3** — you cannot bus-relocate logic that's still buried in the panel; thin first, then decouple.
- **M2 (contracts) precedes M3/M4/M5** — the bus, agent model, and delegator all implement contracts that must exist first (matches arch-doc principle "define these first").
- **M5 after M4** — delegation requires `Agent.can_delegate_to`/`allowed_tools` to be a real per-agent capability.
- **M6 before M7** — the seams and docs land first so the fork swaps (M7) are wiring-only changes; the fork proof is the payoff, everything before it exists to make M7 boring.

## Ripple risks (from arch-doc risks 1–9)

- `Config` singleton stays deliberate and (per M2) documented in `ConfigStore`; tools that call `Config()` keep working.
- Backward compat pin for `~/.kbl/agents/<name>/system_prompt.md` (M4).
- Cancellation: `stop_event` propagation checked in M5 acceptance.
- Context leakage: explicit task+context per delegation, never implicit shared history.