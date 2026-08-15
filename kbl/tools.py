"""Built-in wiki tools exposed to the model via function calling.

Every tool shares the same interface: ``{name, description, parameters,
callable}``. The schemas are sent to the model as the ``tools`` list; when the
model calls one, the app runs the Python function and feeds the result back as
a ``tool`` message. ``builtin_tools`` binds the tools to the active workspace.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

_SEARCH_RESULT_LIMIT = 50
_SNIPPET_LIMIT = 200
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")

# User tool folders live in a top-level "tools" directory; they must not
# pollute the wiki's listing, search, or @-mention suggestions.
_TOOLS_ROOT_NAME = "tools"


def _is_tool_path(rel):
    return rel.parts and rel.parts[0] == _TOOLS_ROOT_NAME


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., str]

    def to_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def run(self, **kwargs):
        return self.func(**kwargs)


class ToolError(Exception):
    """A tool failed to run; the message is fed back to the model."""


def _within(workspace, rel):
    base = Path(workspace).resolve()
    target = (base / str(rel)).resolve()
    if base != target and base not in target.parents:
        raise ToolError(f"Path escapes the workspace: {rel}")
    return target


def list_md_files(workspace):
    """Sorted relative posix paths of all ``.md`` files in the workspace."""
    base = Path(workspace)
    return sorted(
        str(p.relative_to(base))
        for p in base.rglob("*")
        if p.is_file()
        and not p.name.startswith(".")
        and p.suffix.lower() == ".md"
        and not _is_tool_path(p.relative_to(base))
    )


def _list_files(workspace):
    base = Path(workspace)
    if not base.is_dir():
        raise ToolError(f"Not a directory: {base}")
    lines = []
    for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
        if child.name.startswith("."):
            continue
        if _is_tool_path(Path(child.name)):
            continue
        rel = child.relative_to(base)
        if child.is_dir():
            lines.append(f"{rel}/")
            for md in sorted(
                child.rglob("*.md"), key=lambda p: str(p.relative_to(base)).lower()
            ):
                if not md.name.startswith("."):
                    lines.append(str(md.relative_to(base)))
        elif child.suffix.lower() == ".md":
            lines.append(str(rel))
    return "\n".join(lines)


def _read_file(workspace, path):
    target = _within(workspace, path)
    if not target.is_file():
        raise ToolError(f"No such file: {path}")
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"Could not read {path}: {exc}")


def _search_files(workspace, query):
    if not query or not query.strip():
        raise ToolError("Provide a non-empty query to search for.")
    needle = query.strip().lower()
    base = Path(workspace)
    matches = []
    for path in base.rglob("*.md"):
        if path.name.startswith("."):
            continue
        rel = path.relative_to(base)
        if _is_tool_path(rel):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if needle in line.lower():
                snippet = line.strip()[:_SNIPPET_LIMIT]
                matches.append(f"{path.relative_to(base)}:{lineno}: {snippet}")
                if len(matches) >= _SEARCH_RESULT_LIMIT:
                    break
        if len(matches) >= _SEARCH_RESULT_LIMIT:
            break
    if not matches:
        return f"No matches for {query!r} in the workspace."
    return "\n".join(matches)


def _get_headings(workspace, path):
    target = _within(workspace, path)
    if not target.is_file():
        raise ToolError(f"No such file: {path}")
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(f"Could not read {path}: {exc}")
    headings = []
    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            hashes, title = match.groups()
            headings.append(f"{hashes} {title}")
    if not headings:
        return f"(no headings in {path})"
    return "\n".join(headings)


def _get_current_date():
    now = datetime.now().astimezone()
    return (
        now.strftime("%A, %Y-%m-%d %H:%M %Z (UTC%z)")
        .replace("(UTC+0000)", "(UTC)")
    )


def _schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
    }


def builtin_tools(workspace):
    """Return the built-in tools bound to a workspace path."""
    workspace = Path(workspace) if workspace else None
    tools = [
        Tool(
            name="list_files",
            description=(
                "List the wiki's markdown files and folders relative to the "
                "workspace root. Use this to see what the knowledge base contains."
            ),
            parameters=_schema({}),
            func=lambda: _list_files(workspace) if workspace else "No workspace open.",
        ),
        Tool(
            name="read_file",
            description="Return the full contents of a file in the workspace.",
            parameters=_schema(
                {
                    "path": {
                        "type": "string",
                        "description": "Path to a file, relative to the workspace root.",
                    }
                },
                required=["path"],
            ),
            func=lambda path: _read_file(workspace, path),
        ),
        Tool(
            name="search_files",
            description=(
                "Case-insensitive keyword search across the workspace's markdown "
                "files. Returns matching lines with file and line numbers."
            ),
            parameters=_schema(
                {
                    "query": {
                        "type": "string",
                        "description": "Keyword or phrase to search for.",
                    }
                },
                required=["query"],
            ),
            func=lambda query: _search_files(workspace, query),
        ),
        Tool(
            name="get_headings",
            description=(
                "Return the markdown headings of a file, for cheap relevance "
                "checks before reading the whole thing."
            ),
            parameters=_schema(
                {
                    "path": {
                        "type": "string",
                        "description": "Path to a file, relative to the workspace root.",
                    }
                },
                required=["path"],
            ),
            func=lambda path: _get_headings(workspace, path),
        ),
        Tool(
            name="get_current_date",
            description=(
                "Return the current date, time, and weekday so you can resolve "
                "relative dates like 'tomorrow'."
            ),
            parameters=_schema({}),
            func=_get_current_date,
        ),
    ]
    return tools


def run_tool(tools, name, arguments):
    """Run a tool by name with a parsed arguments dict; never raises."""
    tool = next((t for t in tools if t.name == name), None)
    if tool is None:
        return f"Unknown tool: {name}"
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError as exc:
            return f"Could not parse arguments for {name}: {exc}"
    try:
        return tool.run(**arguments)
    except ToolError as exc:
        return str(exc)
    except TypeError as exc:
        return f"Bad arguments for {name}: {exc}"
    except Exception as exc:
        return f"{name} failed: {exc}"


def tool_gating_lines(tools):
    """One-line usage hint per tool, appended to the system prompt."""
    lines = []
    for tool in tools:
        params = tool.parameters.get("properties") or {}
        required = tool.parameters.get("required") or []
        args = ", ".join(
            (name if name in required else f"{name}?")
            for name in params
        )
        if args:
            lines.append(f"- {tool.name}({args}): {tool.description}")
        else:
            lines.append(f"- {tool.name}: {tool.description}")
    return lines
