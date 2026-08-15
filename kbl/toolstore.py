"""Tool discovery and management: built-ins, global tools, workspace tools.

Three sources, one ``{name, description, parameters, callable}`` interface:

- **Built-ins** — ships in app code (the M3 catalog).
- **Global tools** — user-managed root available in every workspace.
- **Workspace tools** — root inside a workspace, only for that workspace.

Each user tool is a folder (OpenClaw-skill style)::

    <tools_root>/<name>/
      SKILL.md   # frontmatter: name + description; body: when/how to use it
      tools.py   # optional: functions, each registering a name, description, schema

``tools.py`` must expose either a ``tools()`` callable or a ``TOOLS`` list
returning ``Tool`` instances (imported from :mod:`kbl.tools`). Disabled tools
(covered by ``disabled_tools`` in config, built-ins included) are omitted from
both the system prompt and the schemas sent to the model.
"""

import importlib.util
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from kbl import config, tools
from kbl.tools import Tool

SKILL_FILENAME = "SKILL.md"
TOOLS_FILENAME = "tools.py"
TOOLS_ROOT_NAME = "tools"

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")

_SKILL_TEMPLATE = """\
---
name: {name}
description: {description}
---

# {name}

This is the home page of the `{name}` tool. Explain when and how the model
should use it: what questions it answers, what its functions do, and any
gotchas.

Implement `tools.py` next to this file with a `tools()` function (or a `TOOLS`
list) returning `Tool` objects imported from `kbl.tools`:

    from kbl.tools import Tool

    def tools():
        return [
            Tool(
                name="my_tool",
                description="What it does.",
                parameters={{'type': 'object', 'properties': {{}}}},
                func=my_function,
            ),
        ]
"""


class ToolStoreError(Exception):
    """A tool-storage operation failed; message is user-facing."""


def validate_name(name):
    if not name:
        raise ToolStoreError("Tool name cannot be empty.")
    if not _NAME_RE.match(name):
        raise ToolStoreError(
            "Tool names may only contain letters, numbers, spaces, "
            "underscores, and dashes."
        )


def global_root():
    """The user-writable root holding global tools (every workspace)."""
    return config.CONFIG_DIR / "tools"


def workspace_root(workspace):
    """The root inside a workspace holding that workspace's tools."""
    return Path(workspace) / TOOLS_ROOT_NAME


@dataclass
class Skill:
    name: str
    source: str
    folder: Path
    description: str
    body: str
    tools: list
    error: str = ""


@dataclass
class ToolCollection:
    enabled_tools: list
    skills: list
    all_skills: list
    warnings: list


# ---- SKILL.md parsing ----


def parse_skill_md(text):
    """Parse ``name``/``description`` frontmatter; return (name, desc, body)."""
    match = re.fullmatch(r"---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return None, "", text.strip()
    front, body = match.groups()
    name = None
    description = ""
    for line in front.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if key == "name":
                name = value
            elif key == "description":
                description = value
    return name, description, body.strip()


# ---- tools.py import ----


def _import_skill_tools(folder):
    """Import the folder's tools.py; return (tools, error) and never raise."""
    path = folder / TOOLS_FILENAME
    if not path.is_file():
        return [], None
    mod_name = "_kbl_skill_" + re.sub(r"\W", "_", str(folder.resolve())).lower()
    try:
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            return [], f"Cannot create module spec for {path}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        items = []
        callable_factory = getattr(module, "tools", None)
        if callable(callable_factory):
            items = callable_factory()
        else:
            items = getattr(module, "TOOLS", None) or []
        result = []
        for item in items:
            if isinstance(item, Tool):
                result.append(item)
            elif isinstance(item, dict):
                result.append(Tool(**item))
            else:
                return [], f"{path}: entry is not a Tool: {item!r}"
        return result, None
    except Exception as exc:  # user code may fail for any reason
        return [], f"{type(exc).__name__}: {exc}"


def scan_folder(folder, source):
    """Scan one folder for a SKILL.md; return a Skill or None if not a tool."""
    skill_md = folder / SKILL_FILENAME
    if not folder.is_dir() or not skill_md.is_file():
        return None
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None
    fm_name, description, body = parse_skill_md(text)
    if not description:
        for line in body.splitlines():
            line = line.strip("# ").strip()
            if line:
                description = line
                break
    skill_tools, error = _import_skill_tools(folder)
    return Skill(
        name=fm_name or folder.name,
        source=source,
        folder=folder,
        description=description,
        body=body,
        tools=skill_tools,
        error=error or "",
    )


def scan_root(root, source):
    """Scan a tools root; return every folder that has a SKILL.md."""
    if not Path(root).is_dir():
        return []
    skills = []
    for folder in sorted(Path(root).iterdir()):
        skill = scan_folder(folder, source)
        if skill:
            skills.append(skill)
    return skills


# ---- collection ----


def _disabled_names(cfg):
    return set(cfg.data.get("disabled_tools") or [])


def collect_tools(workspace, cfg):
    """Collect enabled tools and skills for a workspace.

    Returns a :class:`ToolCollection`. When no workspace is open, returns an
    empty collection (matching M3: no tools without a workspace).
    """
    if not workspace:
        return ToolCollection([], [], [], [])

    builtin = tools.builtin_tools(workspace)
    all_tools = list(builtin)
    seen = {t.name for t in builtin}
    warnings = []

    global_skills = scan_root(global_root(), "global")
    ws_skills = scan_root(workspace_root(workspace), "workspace")
    all_skills = global_skills + ws_skills

    for skill in all_skills:
        if skill.error:
            warnings.append(f"{skill.folder.name}: {skill.error}")
        for t in skill.tools:
            if t.name in seen:
                warnings.append(
                    f"Duplicate tool name {t.name!r} ({skill.folder}) skipped."
                )
            else:
                seen.add(t.name)
                all_tools.append(t)

    disabled = _disabled_names(cfg)
    enabled_tools = [t for t in all_tools if t.name not in disabled]
    enabled_names = {t.name for t in enabled_tools}
    enabled_skills = [
        s for s in all_skills if any(t.name in enabled_names for t in s.tools)
    ]
    return ToolCollection(enabled_tools, enabled_skills, all_skills, warnings)


# ---- enable / disable ----


def set_disabled(cfg, name, disabled):
    """Add or remove a tool name from the config's disabled list."""
    names = list(cfg.data.get("disabled_tools") or [])
    if disabled and name not in names:
        names.append(name)
    elif not disabled and name in names:
        names = [n for n in names if n != name]
    cfg.data["disabled_tools"] = names
    cfg.save()


# ---- storage operations ----


def create_skill(root, name, description="", body=""):
    """Create a new tool folder under a root from the default template."""
    validate_name(name)
    folder = Path(root) / name
    if folder.exists():
        raise ToolStoreError(f"Tool {name!r} already exists.")
    folder.mkdir(parents=True, exist_ok=False)
    text = _SKILL_TEMPLATE.format(
        name=name,
        description=description or f"The {name} tool.",
    )
    if body:
        text = text.rstrip("\n") + "\n\n" + body.strip() + "\n"
    (folder / SKILL_FILENAME).write_text(text, encoding="utf-8")
    return folder


def delete_skill(root, name):
    folder = Path(root) / name
    if not folder.is_dir():
        raise ToolStoreError(f"Tool {name!r} does not exist.")
    shutil.rmtree(folder)


def rename_skill(root, old, new):
    validate_name(new)
    old_folder = Path(root) / old
    new_folder = Path(root) / new
    if not old_folder.is_dir():
        raise ToolStoreError(f"Tool {old!r} does not exist.")
    if new_folder.exists():
        raise ToolStoreError(f"Tool {new!r} already exists.")
    old_folder.rename(new_folder)


# ---- sample tool ----


def sample_dir(name="todo"):
    """Path to a bundled sample tool folder (ship-shipped, read-only)."""
    return Path(__file__).with_name("sample_tools") / name


def install_sample(root, name="todo"):
    """Copy a bundled sample tool into a tools root; returns the new folder."""
    src = sample_dir(name)
    if not src.is_dir():
        raise ToolStoreError(f"No sample tool {name!r} bundled with the app.")
    validate_name(name)
    dst = Path(root) / name
    if dst.exists():
        raise ToolStoreError(f"A tool named {name!r} already exists.")
    shutil.copytree(src, dst)
    return dst