# Knowledge Base Librarian — System Architecture

> A living document. This describes the system's actual structure today and the evolution toward a pluggable, event-driven framework.

## 1. System Intent

The application is a **desktop knowledge-management agent** built on a decoupled LLM harness. At its core is a powerful abstraction: **a workspace = a directory = a knowledge base.** This abstraction is the foundation for the "rock solid framework" — because everything downstream (file trees, chat context, tool access) derives from a single concept of "active knowledge."

The stated north star:
> **Narrow AI guarantee** — whatever is enabled in a given run is all the model can reach. This keeps behavior predictable and testable.

---

## 2. The Six Major Areas (your decomposition)

| # | Area | Responsibility | Framework concern |
|---|------|---------------|-------------------|
| 1 | **Tkinter (foundation)** | Widgets, theming, event loop | Must stay a *view layer only* |
| 2 | **Main Window (orchestration)** | Layout + panel composition | Must become a *mediator*, not a god-object |
| 3 | **Directory Tree (Library)** | Browse/manage files | Emits events; must not depend on Chat |
| 4 | **Display Area (Display)** | Render selected content | Stateless view |
| 5 | **Chat Panel (UI for harness)** | User conversation surface | Emits "send" events; must not call harness directly |
| 6 | **LLM Harness (brain)** | Compose request, call server, run tools | Pure service; zero Tkinter imports |

---

## 3. Current Architecture — What It Actually Is

Reading the code reveals the current system is a **three-layer application** with an important architectural tension:

```
┌─────────────────────────────────────────────────┐
│                    Tkinter UI                    │
│  MainWindow (tk.Tk)                              │
│  ├── FileTreePanel (on_open=...)  ← callbacks   │
│  ├── EditorPanel (config=...)                     │
│  └── ChatPanel (on_configure=...)  ← callbacks   │
├─────────────────────────────────────────────────┤
│                   Services                        │
│  WorkspaceManager | Config | ConversationStore   │
│  Agents | Context | Tools | ToolStore            │
├─────────────────────────────────────────────────┤
│                 Data / Model                    │
│  workspaces (in-memory) | config.json | convs   │
└─────────────────────────────────────────────────┘
```


### Key insight from the code

The current coupling model uses **callbacks passed in the constructor**. Look at `MainWindow`:

```python
self.panels["tree"] = FileTreePanel(self, on_open=self._open_file)
self.panels["chat"] = ChatPanel(
    self,
    on_configure_server=self._show_server_config,
    on_manage_agents=self._show_agent_manager,
)
```


And `ChatPanel` reaches into `self.master`:

```python
config = self.master.config
workspace = self.master.workspaces.active
```


This is the **primary architectural risk.** The panels depend on `self.master` for config, workspaces, and cross-panel actions. This works for a prototype but will collapse as you add more panels. **This is exactly the "giant callback" smell the tkinter guidelines warn against.**

### The good news (it's already well-siloed)

Several components are **pure services with zero Tkinter imports** — these are the framework's future building blocks:

- **`chat_client.py`** — pure OpenAI-compatible client. No Tkinter. Ready to reuse.
- **`tools.py`** — the tool execution engine (`Tool.run()`, `run_tool()`). Pure Python.
- **`context.py`** — system message composition. Pure Python.
- **`agents.py`** — agent persona management (inferred). Pure Python.
- **`workspaces.py`** — workspace state management. Pure Python.
- **`conversations.py`** — conversation persistence. Pure Python.

**This is your strongest asset for the framework:** the "brain" is already decoupled. You just need to formalize the contracts between it and the UI.

---

## 4. The Event-Driven Transformation

Your goal is event-driven, swappable components. Here is the target architecture:

### 4.1 Introduce an Event Bus (Mediator)

Replace `self.master.config` / `self.master.workspaces` and cross-panel callbacks with a **central event bus**. Components emit events and subscribe to events — they never reach into each other.

```
┌─────────────────────────────────────────────────┐
│                   Event Bus                       │
│  (publish / subscribe, typed events)             │
├─────────────────────────────────────────────────┤
│  Events:                                        │
│  - WorkspaceSelected(workspace: Path)            │
│  - FileOpened(path: Path)                        │
│  - UserSent(message: str, attachments: [...])    │
│  - AssistantReply(stream: Iterator[StreamEvent]) │
│  - ToolRequested(name: str, args: dict)          │
│  - ToolResult(name: str, result: str, error: str|None) │
│  - AgentChanged(agent_id: str)                   │
│  - DelegationRequested(caller_id: str, agent_id: str, task: str, context: list[dict], tool_allowlist: set[str]|None) │
│  - SubagentStarted(caller_id: str, agent_id: str, task_id: str) │
│  - SubagentEvent(task_id: str, event: StreamEvent) │
│  - SubagentCompleted(task_id: str, result: str, tool_calls: list[dict]|None) │
│  - SubagentFailed(task_id: str, error: str)      │
└─────────────────────────────────────────────────┘
        ▲                    ▲                    ▲
        │                    │                    │
  FileTreePanel      EditorPanel          ChatPanel
```


**Why this matters for your StableDiffusion fork:** you'd delete `ChatPanel` and `EditorPanel`, add an `ImageCanvas` and a `DiffusionPromptPanel`. None of the core services (workspaces, config, event bus) change. **This is the whole point of the framework.**

### 4.2 The LLM Harness as a Service (Orchestrator)

Currently the "harness" is spread across `chat_client.py` + `tools.py` + `context.py` + `agents.py`. For a framework, unify these into a single `Harness` service with a clean contract. The harness also acts as an **orchestrator** responsible for subagent delegation.

```python
class Harness(Protocol):
    async def send(
        self,
        messages: list[dict],
        tools: list[Tool],
        workspace: Workspace | None,
        stop_event: Event,
        active_agent: str | None = None,
        parent_task_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        ...
```


Where `StreamEvent` is a typed union: `Content(chunk) | Reasoning(chunk) | ToolCall(name, args) | ToolResult(name, text) | Done(text) | Error(exc)`. (Subagent-scoped events may be correlated via `task_id`/`agent_id` and emitted on the event bus; the core `StreamEvent` types remain backward compatible.)

Key design points:

- **Orchestration**: The harness decides whether to answer directly or delegate to a subagent, respecting each agent's capabilities and allowed tools. Delegation is a first-class control flow.
- **Delegation model (tool-first, pluggable)**: A model can emit a `delegate(agent_id, task, context)` tool call (consistent with the existing tool loop). The harness executes delegation by invoking the target subagent with an isolated scope (separate conversation/thread, tool allowlist, workspace scope) and returns results back to the caller (e.g., folded into a tool result or correlated via subagent events).
- **Isolation**: Each subagent invocation gets its own conversation/thread scope, `stop_event`, and explicit tool permissions. Parent context is passed explicitly (never implicit global sharing) to avoid context leakage.
- **Backend-agnostic**: The `chat_client.py` OpenAI-compatible client is one backend. Adding Ollama, llama.cpp, or a StableDiffusion backend means adding a *new* harness implementation, not changing the UI.
- **Unification**: Orchestration (main → subagents, including nested delegation) lives entirely inside the harness (a pure service, zero Tkinter imports).

### 4.3 Concurrency Model (critical)

The current code uses **threads + queues** (see `_stream_worker`, `_drain_queue` in ChatPanel). This is correct, but the wiring is buried inside the panel. Move it into the harness:

- UI thread → publishes `UserSent` event → harness runs on worker thread.
- Harness yields stream events → event bus marshals them back to the UI thread via `root.after(...)`.
- **Never touch Tkinter from a worker thread.** The guidelines are explicit; the harness must own this discipline.
- **Delegation concurrency:** Delegated subagents run on worker threads (same harness concurrency model). Each subagent invocation uses its own `stop_event`; nested delegation propagates cancellation down the delegation tree. All subagent events are marshaled to the UI thread via `root.after(...)`. No Tkinter access from worker threads.

---

## 5. The Contracts (your deliverable #2)

You said: *"what the components should be siloed, what the contracts are."* These are the **Python `Protocol`s** that define each boundary. Define these first, before writing implementation.

| Contract | Between | Purpose |
|----------|---------|---------|
| `WorkspaceProvider` | MainWindow/Services → WorkspaceManager | "What is the active knowledge base right now?" |
| `ConfigStore` | All services → Config | Persistent JSON state, per-instance active selection |
| `ChatHarness`/`Harness` | ChatPanel → Harness | "Send a message, stream the reply (including delegated turns)" |
| `ToolRegistry` | Harness → Tools | "Which tools exist and how do they run? (with per-agent/tool allowlists)" |
| `FileRepository` | Tree/Editor/Tools → FS | "List, read, write, create files in a workspace" |
| `EventBus` | All panels/services | "Publish/subscribe cross-component messages (including subagent/delegation events)" |
| `DisplayRenderer` | Main → Display | "Render arbitrary content (md, image, etc.)" |
| `Agent` | Registry → Agent impl | "Agent identity, role, system prompt, capabilities (allowed tools), can_delegate_to" |
| `AgentRegistry` | Harness/Orchestrator/UI → Agents | "List/get/create/update/delete agents; get active; resolve subagents; validate names" |
| `SubagentRegistry` | Harness → Agents | "Enumerate callable subagents, relationships, tool allowlists, and delegation constraints" |
| `Delegator`/`Orchestrator` | Harness → Subagents | "Delegate(task_req) → AsyncIterator[StreamEvent]/DelegationResult with isolated scope" |
| `DelegationRequest` | Orchestrator (internal) | "(agent_id, task, messages, context, tool_allowlist, parent_task_id, workspace, stop_event)" |
| `DelegationResult` | Orchestrator → Caller | "(text, tool_calls, artifacts, error) correlated to task_id" |

**This is the key deliverable:** write each `Protocol` in a `contracts.py` module. The current `agents.py` models single-active persona storage; extend it to satisfy `AgentRegistry`/`SubagentRegistry` (adding metadata like `description`, `role`, `allowed_tools`, `parent`, `can_delegate_to`, `max_turns`, `max_depth`) while preserving backward compatibility. Existing pure services (`chat_client.py`, `tools.py`, `context.py`, `agents.py`, `conversations.py`, `workspaces.py`, `toolstore.py`) should be verified/refactored to explicitly satisfy relevant contracts.

---

## 6. Documentation Per Component (deliverable #3)

Each framework component needs a doc with a consistent template. Propose this:

```markdown
## <Component>
- **Purpose:** one paragraph
- **Location:** kbl/<file>.py
- **Inputs:** what it receives (typed)
- **Outputs:** what it emits (typed)
- **Dependencies:** what it may import/use (pure = no Tkinter)
- **Events:** emits / subscribes (including subagent/delegation events if applicable)
- **Contracts it satisfies:** e.g. AgentRegistry, SubagentRegistry, Delegator, ToolRegistry
- **Subagents/Delegation:** whether it can delegate, be delegated to, or neither; delegation scope and tool allowlists
- **Isolation & scope:** conversation/thread scope, what context it receives vs. does not pass, cancellation behavior
- **Testability:** how to test without a GUI
- **Fork implications:** what breaks if you remove this panel?
```


For example, the **ChatPanel** doc must explicitly state: *"This is a **view**. It must never import or reach into file system logic. It only emits `UserSent` and renders `AssistantReply`."* That statement is what makes the StableDiffusion fork possible — you can delete this file entirely.

---

## 7. Milestones Toward the Framework

| Phase | Focus | Outcome |
|-------|-------|---------|
| **F0** | Write `contracts.py` (incl. Agent, AgentRegistry, SubagentRegistry, Delegator/Orchestrator, DelegationRequest/Result) | Boundaries defined on paper/code |
| **F1** | Introduce `EventBus`, replace `self.master` cross-panel refs | Panels become decoupled |
| **F2a** | Extend `agents.py` → full Agent/Subagent model + metadata | Subagents concept exists (registry) |
| **F2b** | Delegation + Orchestrator in Harness (tool-first delegate, isolation, task_id correlation, cancellation) | Delegation works end-to-end |
| **F3** | Write per-component docs for all pure services (including subagent/delegation fields) | New devs/forks understand the system |
| **F4** | Add a second harness (e.g., StableDiffusion backend) | Prove the framework is swappable |
| **F5** | Add a second display type (image canvas) | Prove the framework is pluggable |

---

## 8. Risks & Recommendations

1. **`self.master` coupling is the #1 risk.** It's the single biggest barrier to the fork. Fix it first (F1).
2. **Config is a process-wide singleton** (`_DEFAULT_INSTANCE`). This is intentional (tools need it) but couples tool execution to the running app. Keep it, but make it explicit in the `ConfigStore` contract.
3. **The "harness" is currently 4 modules.** Consolidate into one service so the framework has a single "brain" entry point.
4. **Pure services are your foundation.** `chat_client.py`, `tools.py`, `context.py`, `conversations.py`, `agents.py`, `workspaces.py`, `toolstore.py` are already GUI-free. Protect them — never let Tkinter leak in.
5. **Delegation complexity**: Start with single-level delegation and a tool-first `delegate(agent_id, task, context)` approach. Cap recursion depth, max turns per subagent, and total delegated turns to avoid runaway delegation.
6. **Context leakage**: Pass explicit context per delegation (task + relevant context). Never implicitly share full message history across subagents; prefer scoped threads/sessions. Document what is passed vs. excluded.
7. **Tool scoping**: Enforce per-agent tool allowlists in the Harness/ToolRegistry (principle of least privilege). Subagents must only access tools explicitly permitted.
8. **Backward compatibility**: Extend `agents.py` to support subagents/metadata without breaking existing single-agent behavior or storage layout (`~/.kbl/agents/<name>/system_prompt.md`).
9. **Nested cancellation & cleanup**: `stop_event` must propagate to child subagents on cancel or abort. Ensure tasks are cleaned up on completion, error, or cancellation.

