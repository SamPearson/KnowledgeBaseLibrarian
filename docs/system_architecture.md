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
│  - AssistantReply(stream: Iterator[str])         │
│  - ToolRequested(name: str, args: dict)          │
│  - ToolResult(result: str)                       │
└─────────────────────────────────────────────────┘
        ▲                    ▲                    ▲
        │                    │                    │
  FileTreePanel      EditorPanel          ChatPanel
```


**Why this matters for your StableDiffusion fork:** you'd delete `ChatPanel` and `EditorPanel`, add an `ImageCanvas` and a `DiffusionPromptPanel`. None of the core services (workspaces, config, event bus) change. **This is the whole point of the framework.**

### 4.2 The LLM Harness as a Service

Currently the "harness" is spread across `chat_client.py` + `tools.py` + `context.py` + `agents.py`. For a framework, unify these into a single `Harness` service with a clean contract:

```python
class Harness(Protocol):
    async def send(
        self,
        messages: list[dict],
        tools: list[Tool],
        workspace: Workspace | None,
        stop_event: Event,
    ) -> AsyncIterator[StreamEvent]:
        ...
```


Where `StreamEvent` is a typed union: `Content(chunk) | Reasoning(chunk) | ToolCall(name, args) | ToolResult(name, text) | Done(text) | Error(exc)`.

The harness is **backend-agnostic** — the `chat_client.py` OpenAI-compatible client is one backend. Adding Ollama, llama.cpp, or a StableDiffusion backend means adding a *new* harness implementation, not changing the UI.

### 4.3 Concurrency Model (critical)

The current code uses **threads + queues** (see `_stream_worker`, `_drain_queue` in ChatPanel). This is correct, but the wiring is buried inside the panel. Move it into the harness:

- UI thread → publishes `UserSent` event → harness runs on worker thread.
- Harness yields stream events → event bus marshals them back to the UI thread via `root.after(...)`.
- **Never touch Tkinter from a worker thread.** The guidelines are explicit; the harness must own this discipline.

---

## 5. The Contracts (your deliverable #2)

You said: *"what the components should be siloed, what the contracts are."* These are the **Python `Protocol`s** that define each boundary. Define these first, before writing implementation.

| Contract | Between | Purpose |
|----------|---------|---------|
| `WorkspaceProvider` | MainWindow → WorkspaceManager | "What is the active knowledge base right now?" |
| `ConfigStore` | All services → Config | Persistent JSON state, per-instance active selection |
| `ChatHarness` | ChatPanel → Harness | "Send a message, stream the reply" |
| `ToolRegistry` | Harness → Tools | "Which tools exist and how do they run?" |
| `FileRepository` | Tree/Editor → FS | "List, read, write, create files in a workspace" |
| `EventBus` | All panels | "Publish/subscribe cross-component messages" |
| `DisplayRenderer` | Main → Display | "Render arbitrary content (md, image, etc.)" |

**This is the key deliverable:** write each `Protocol` in a `contracts.py` module. Then `chat_client.py`, `tools.py`, `context.py` already satisfy several of them — verify and refactor to *explicitly* satisfy them.

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
- **Events:** emits / subscribes
- **Contracts it satisfies:** e.g. ConfigStore, ToolRegistry
- **Testability:** how to test without a GUI
- **Fork implications:** what breaks if you remove this panel?
```


For example, the **ChatPanel** doc must explicitly state: *"This is a **view**. It must never import or reach into file system logic. It only emits `UserSent` and renders `AssistantReply`."* That statement is what makes the StableDiffusion fork possible — you can delete this file entirely.

---

## 7. Milestones Toward the Framework

| Phase | Focus | Outcome |
|-------|-------|---------|
| **F0** | Write all `contracts.py` Protocols | Boundaries defined on paper/code |
| **F1** | Introduce `EventBus`, replace `self.master` cross-panel refs | Panels become decoupled |
| **F2** | Extract harness from ChatPanel into `Harness` service | Concurrency lives in the harness, not the UI |
| **F3** | Write per-component docs for all pure services | New devs/forks understand the system |
| **F4** | Add a second harness (e.g., StableDiffusion backend) | Prove the framework is swappable |
| **F5** | Add a second display type (image canvas) | Prove the display is pluggable |

---

## 8. Risks & Recommendations

1. **`self.master` coupling is the #1 risk.** It's the single biggest barrier to the fork. Fix it first (F1).
2. **Config is a process-wide singleton** (`_DEFAULT_INSTANCE`). This is intentional (tools need it) but couples tool execution to the running app. Keep it, but make it explicit in the `ConfigStore` contract.
3. **The "harness" is currently 4 modules.** Consolidate into one service so the framework has a single "brain" entry point.
4. **Pure services are your foundation.** `chat_client.py`, `tools.py`, `context.py`, `conversations.py` are already GUI-free. Protect them — never let Tkinter leak in.

