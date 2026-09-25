# Knowledge Base Librarian

Knowledge Base Librarian (KBL) is a desktop Markdown knowledge base with an AI assistant built into it. It works directly with a folder on your computer: you can browse and edit Markdown files in the app, then ask a configured language model to search, explain, organize, or update that knowledge base.

KBL is local-first: your files stay in ordinary folders and the application stores its settings under `~/.kbl/`. The LLM itself is not bundled, however. Prompts, attached file contents, and any files returned by enabled tools are sent to the OpenAI-compatible server you configure, so choose a provider and privacy settings appropriate for your data.

## What it can do

- Manage one or more local Markdown workspaces.
- Browse folders and Markdown files, edit them, and switch between edit and rendered display modes.
- Chat with a model using an OpenAI-compatible `/v1` API.
- Let the model inspect workspace files through tools.
- Create Markdown files and update existing files with timestamped backups.
- Keep multiple workspace-scoped conversations.
- Define agents with custom system prompts and optional delegation relationships.
- Add custom tools, either globally or for one workspace.
- Switch layouts and themes while preserving panel sizes.

KBL reads files on demand. It is not a hosted service, a document-ingestion pipeline, a vector database, or a continuous file watcher. The Stable Diffusion harness in the source tree is an architectural proof of concept; image generation is not a normal feature of the current desktop UI.

## Requirements

- Python 3.10 or newer.
- A graphical desktop session with Tk support. A headless Linux installation may also need the operating system’s Tk package, commonly named `python3-tk`.
- An OpenAI-compatible LLM server that supports chat completions and tool calling.
- Read/write permission for the folders you choose as workspaces.

There is no model server or API key bundled with the application.

## Install and launch

From a checkout of the project:

```bash
cd /path/to/knowledge_base_librarian
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows, activate the environment with `venv\Scripts\activate` and use `python` in place of `python3`.

You can open a workspace at launch:

```bash
python app.py --workspace "/path/to/notes"
```

The `--workspace` option registers and selects that folder for this application session. It does not change the future default selected by the normal Workspace menu. Without the option, KBL uses its saved default workspace, if one exists. The module entry point is equivalent:

```bash
python -m kbl --workspace "/path/to/notes"
```

## First run

1. Choose **Workspace → Open Folder...** and select a folder for your notes. An empty folder is fine.
2. Use **File → New Markdown File...** or the file tree’s right-click menu to create a first note.
3. Open **Chat → Server Configuration...**, enter your server URL and model, then save.
4. Select a conversation and send a question such as, “List the Markdown files in this workspace and summarize their headings.”
5. Use **View** to choose a layout, and use **Theme → Select Theme...** to change the appearance.

If you want to give the model workspace-specific instructions, create a non-empty `instructions.md` at the workspace root. When present, it replaces KBL’s default workspace guidance. KBL does not automatically reload that file, so update the chat or restart the application after changing it if necessary.

## Workspaces

A workspace is simply the selected local directory and its subdirectories. The current workspace determines what the file tree shows, which files tools may access, and which conversations are available.

Use **Workspace → Workspaces...** to:

- add a folder;
- remove a folder from the application’s workspace list;
- activate a folder; or
- close the dialog without making a change.

Activating a workspace from the menu also makes it the default for future launches. A workspace supplied with `--workspace` is session-specific instead. Switching workspaces persists the current chat before changing the file tree, editor, tools, and conversation selection.

The registered workspace list is application configuration; it does not move or copy your documents. Keep separate workspaces for separate knowledge bases, projects, or trust boundaries.

## Browsing and editing Markdown

The file tree displays folders and visible `.md` files recursively. Hidden files and directories are omitted. The tree does not automatically follow changes made by another program, so use **Refresh** when files are created, renamed, or removed outside KBL.

### File tree actions

- Double-click a file, or select it and press **Enter**, to open it in the editor.
- Double-click a folder, or select it and press **Enter**, to expand or collapse it.
- Right-click to create a file or folder, refresh the tree, or delete the selected item.
- **New File...** appends `.md` when the name does not already end in that suffix.
- **Delete** is permanent. Deleting a folder removes the folder and all of its contents after confirmation.
- KBL currently has no file-rename action; rename files in your operating system or editor, then refresh the tree.

### Editing and display

- The editor reads and writes UTF-8 text.
- An asterisk (`*`) next to the file name means the editor has unsaved changes.
- Use **Save** or `Ctrl-S` to save.
- Use **Display** or `Ctrl-E` to switch between editing and rendered Markdown.
- The display view is a rendering of the current editor text. If a file was changed by the model or another application, reopen it or refresh the tree before relying on the displayed content.

## Configure an LLM server

Open **Chat → Server Configuration...**. The dialog accepts:

- **Server URL**: the complete OpenAI-compatible API base URL, including the path suffix. For example, use `http://localhost:11434/v1` for Ollama or `http://localhost:8080/v1` for a llama.cpp server.
- **Model**: a model identifier understood by that server. You can type one manually or use **Fetch Models...** after entering a server URL.
- **API Key (optional)**: a bearer key for servers that require one.
- **Max tool rounds**: the maximum number of model/tool iterations for one request. The default is 8; values below 1 are clamped to 1.

The client calls `<server URL>/models` when fetching models and `<server URL>/chat/completions` for chat. Enter the full `/v1` base URL rather than appending the API path yourself in the field. A server must implement the chat-completions and tool-call format expected by KBL.

Most local servers ignore the API key. If the field is blank, the client sends the placeholder value `not-needed`; it does not read a key from an environment variable or `.env` file.

Settings are saved in `~/.kbl/config.json`, including the API key in plaintext. Protect that file with the permissions appropriate for your machine. KBL does not include a model server, account management, or secret vault.

A request that keeps making tool calls stops at the configured round limit and reports `Stopped after N tool rounds.` Narrow the request or raise the limit for larger research tasks.

## Use the chat panel

The chat panel provides model, agent, and conversation selectors along with **Server**, **New**, **Rename**, **Send**, and **Stop** controls. A server and model are required before sending.

- Press `Enter` to send.
- Press `Shift-Enter` to insert a line break.
- Use **New** to start an empty conversation and **Rename** to give the current conversation a recognizable name.
- Use **Stop** to request cancellation. Stop is cooperative: it signals the worker but cannot forcibly terminate a request already blocked in a network call.
- The active agent’s system prompt is sent with each request.

The model does not receive every workspace file automatically. It starts with the conversation, workspace/agent instructions, and any attached files. It can use enabled tools to inspect additional workspace files, so the exact file contents sent to the server depend on the model’s tool calls and the tools you have enabled.

### Attach a file with `@`

Type `@` in the message box to open a list of Markdown files in the active workspace. Choose a file to attach it. The complete file contents are included in the message sent to the model, rather than just its path.

A file can be attached only when it exists inside the active workspace. Hidden files and files outside the workspace cannot be attached this way. Check the contents before sending when the provider is remote or shared.

### Conversations and privacy

Conversations are scoped to a workspace and stored as JSON under `~/.kbl/conversations/`. Switching workspaces therefore presents a different set of conversations. Conversation history can contain prompts, file contents, tool results, and model responses, even when the source Markdown remains in the workspace.

If a conversation is not available after reopening the app, confirm that the same workspace path is active. Workspace-specific conversation storage is based on the workspace path.

## Tools and file safety

Tools are the actions KBL exposes to the model. Open **Chat → Tools...** to inspect, enable, or disable them. Disabling a tool removes both its description and its schema from the model request; built-in tools can be disabled even though they cannot be renamed or deleted.

### Built-in tools

| Tool | Purpose | Writes files |
| --- | --- | --- |
| `list_files` | List visible files and folders in the workspace. | No |
| `read_file` | Read a workspace-contained file. | No |
| `search_files` | Search case-insensitive literal text and return matching lines. | No |
| `get_headings` | Extract Markdown headings. | No |
| `get_current_date` | Return the current date. | No |
| `create_file` | Create a Markdown file. | Yes |
| `edit_file` | Replace a file’s complete contents. | Yes |

Search is literal and case-insensitive, returns at most 50 results, and shows short snippets. Hidden entries and the workspace’s top-level `tools/` directory are excluded from normal file listing and search. `read_file` can still read a workspace-contained non-Markdown file when the model asks for it.

`edit_file` expects the complete replacement text; it is not a patch operation. Before writing, KBL creates a timestamped backup in the sibling `backups/` directory and returns a unified diff in the chat history. Backups are a safety aid, not a transactional versioning system: there is no locking or conflict resolution for simultaneous editors.

### Read-only chat mode

To prevent the model from creating or changing workspace files:

1. Open **Chat → Tools...**.
2. Select `create_file`, choose **Disable**, and repeat for `edit_file`.
3. Leave the read tools enabled if the model should be able to inspect the knowledge base.

Also consider disabling custom tools that have side effects. Review tool calls and file diffs before allowing writes, especially when using a remote model.

### Custom tools

Tools are discovered from three locations:

- built into the application;
- global tools under `~/.kbl/tools/`; and
- workspace tools under `<workspace>/tools/`.

Each user tool is a directory containing a `SKILL.md` file and, optionally, a `tools.py` file. The skill document describes when and how the model should use the tool. A Python tool can expose either a `tools()` function or a `TOOLS` list of `Tool` objects. The **New Global...** and **New Workspace...** buttons in **Chat → Tools...** create the standard folder and `SKILL.md` template for you.

For example, the layout is:

```text
~/.kbl/tools/my-tool/
├── SKILL.md
└── tools.py
```

**Install Sample** copies the bundled `todo` sample into a global or workspace tool directory. It is a useful starting point, but review the generated Python before enabling it.

Custom `tools.py` files execute in the KBL application process and are not sandboxed. Install or edit only code you trust. A tool can access anything the application process can access, and its behavior is not limited to the workspace unless its own code enforces that restriction.

## Agents and delegation

**Chat → Agents...** manages assistant identities. Each agent has a saved system prompt under `~/.kbl/agents/<name>/system_prompt.md` and optional metadata. The dialog lets you:

- create, rename, and delete agents;
- edit and save a system prompt;
- list comma-separated agents under **Can delegate to**; and
- mark an agent as active with **Set Active**.

The active agent is also selected from the chat panel. Its system prompt is sent with every message, so keep it focused on the role and behavior you want rather than treating it as a replacement for the tool allowlist.

Delegation is opt-in and model-driven. A parent agent can only delegate to agents listed for it; the child receives a fresh, scoped context and returns its result to the parent. Delegation does not automatically restrict a child’s actions beyond the tools and limits configured for that run. Start with read-only tools and simple delegation relationships, then expand permissions deliberately.

## Layouts and themes

The **View** menu offers these layouts:

- `tree-editor-chat` — file tree, editor, and chat;
- `tree-editor` — file tree and editor;
- `editor-chat` — editor and chat; and
- `editor` — editor only.

Panel widths are remembered per layout. **View → Toggle Edit/Display** is a shortcut for switching the editor mode. **Theme → Select Theme...** changes the selected theme; **Theme → Edit Theme...** opens the theme editor.

## State, backups, and security

KBL stores data in a few different places:

| Location | Contents |
| --- | --- |
| Your workspace | The Markdown files, folders, `instructions.md`, custom workspace tools, and generated `backups/` files. |
| `~/.kbl/config.json` | Workspaces, layout, theme, server, model, API key, disabled tools, active agent, and conversation selection. |
| `~/.kbl/conversations/` | Workspace-scoped conversation history. |
| `~/.kbl/agents/` | Agent system prompts and optional delegation metadata. |
| `~/.kbl/tools/` | Global custom tool folders. |
| `<workspace>/tools/` | Tools available only in that workspace. |
| `<edited-file-directory>/backups/` | Timestamped backups created by `edit_file`. |

Before using a remote model, remember that the following may leave your machine:

- your chat messages and attached Markdown contents;
- `instructions.md` and the active agent’s system prompt;
- file contents returned by enabled read/search tools; and
- tool results and generated diffs.

Use a local endpoint when appropriate, restrict workspace selection to trusted directories, protect `~/.kbl/`, and review custom tool code. KBL does not encrypt the API key or conversation files at rest.

## Troubleshooting

### The window will not start

- Activate the virtual environment and reinstall `requirements.txt`.
- Run the application from a graphical session, not a headless shell.
- On Linux, check that the system Tk package is installed.
- Run `python app.py` from the project directory so the `kbl` package can be imported.

### `ModuleNotFoundError` appears

Make sure the virtual environment is active and install the runtime requirements:

```bash
python -m pip install -r requirements.txt
```

Use `requirements-dev.txt` instead when you also want the test dependency.

### Fetch Models fails

Check that:

- the server is running;
- the URL includes the correct API prefix, commonly `/v1`;
- the URL uses the correct scheme, host, and port; and
- the server exposes the OpenAI-compatible `/models` endpoint.

You can always type a model identifier manually if the server does not implement model listing.

### The model cannot answer or the chat stops early

Confirm that the model supports the tool-calling format required by the server. If a request repeatedly invokes tools, reduce its scope or increase **Max tool rounds**. A round-limit stop is reported in the chat; it is not a network error.

### A file does not appear

Check that a workspace is active, the file has a `.md` extension, and it is not hidden. Use the file tree’s **Refresh** button after changing the directory outside KBL.

### Changes made by the model are not visible

Use **Refresh** and reopen the file. KBL does not watch the filesystem for external changes, and a file edited by a tool may not be automatically loaded into an already-open editor buffer.

### Stop does not return immediately

Stop requests cooperative cancellation. A request blocked inside the model or tool call can finish or time out first. The configured chat client uses a 60-second timeout for network chat requests.

### A custom tool is missing or fails

Open **Chat → Tools...** after confirming the tool is in `~/.kbl/tools/` or `<workspace>/tools/`, has a `SKILL.md`, and is not disabled. A `tools.py` load error is shown in the tool details. Remember that custom Python is executed in-process; use only trusted code and check its filesystem and network behavior.

## Development checks

Install development dependencies and run the test suite from the project directory:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The repository currently has no configured lint or type-check command. For design and implementation context, see [`docs/pitch.md`](docs/pitch.md), [`docs/system_architecture.md`](docs/system_architecture.md), and the component notes under [`docs/components/`](docs/components/). Those documents are developer notes; this README describes the current user-facing behavior.
