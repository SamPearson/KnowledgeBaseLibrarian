"""Agent system prompts: one directory per agent under ~/.kbl/agents.

Each agent is a directory containing a ``system_prompt.md`` file that is sent
as the system message on every turn. Users can create, edit, delete, and
switch between agents at any time.
"""

import re
import shutil
from pathlib import Path

from kbl.config import CONFIG_DIR

AGENTS_DIR = CONFIG_DIR / "agents"
PROMPT_FILE = "system_prompt.md"
DEFAULT_AGENT = "assistant"
DEFAULT_SYSTEM_PROMPT = (
    "You are KBL, a helpful assistant running on the user's homelab."
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")


class AgentError(Exception):
    """Agent name or storage problem."""


def validate_name(name):
    name = name.strip()
    if not name:
        raise AgentError("Agent name cannot be empty.")
    if not _NAME_RE.match(name):
        raise AgentError(
            "Agent names may contain letters, digits, spaces, hyphens, "
            "and underscores only."
        )
    return name


def agent_dir(name):
    return AGENTS_DIR / validate_name(name)


def prompt_path(name):
    return agent_dir(name) / PROMPT_FILE


def list_agents():
    """Sorted names of agents that have a system_prompt.md file."""
    seeded = seed_default()
    if not AGENTS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in AGENTS_DIR.iterdir()
        if p.is_dir() and (p / PROMPT_FILE).is_file()
    ) or ([DEFAULT_AGENT] if seeded else [])


def seed_default():
    """Create the default agent on first run (missing or empty agents dir)."""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    if any(AGENTS_DIR.iterdir()):
        return False
    dir_path = AGENTS_DIR / DEFAULT_AGENT
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / PROMPT_FILE).write_text(
        DEFAULT_SYSTEM_PROMPT + "\n", encoding="utf-8"
    )
    return True


def create_agent(name, prompt=DEFAULT_SYSTEM_PROMPT):
    name = validate_name(name)
    path = prompt_path(name)
    if path.exists():
        raise AgentError(f"Agent {name!r} already exists.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt + "\n", encoding="utf-8")
    return name


def get_prompt(name):
    path = prompt_path(name)
    if not path.is_file():
        raise AgentError(f"Agent {name!r} has no system prompt.")
    return path.read_text(encoding="utf-8")


def set_prompt(name, prompt):
    path = prompt_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt + "\n", encoding="utf-8")


def rename_agent(old, new):
    old = validate_name(old)
    new = validate_name(new)
    old_dir = agent_dir(old)
    new_dir = agent_dir(new)
    if not (old_dir / PROMPT_FILE).is_file():
        raise AgentError(f"Agent {old!r} does not exist.")
    if (new_dir / PROMPT_FILE).exists():
        raise AgentError(f"Agent {new!r} already exists.")
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    old_dir.rename(new_dir)
    return new


def delete_agent(name):
    path = agent_dir(name)
    if not (path / PROMPT_FILE).is_file():
        raise AgentError(f"Agent {name!r} does not exist.")
    shutil.rmtree(path)


def active_agent(config):
    """Name of the currently selected agent, falling back to a valid one."""
    name = (config.data.get("active_agent") or "").strip()
    if name and (AGENTS_DIR / name / PROMPT_FILE).is_file():
        return name
    agents = list_agents()
    if agents:
        return agents[0]
    seed_default()
    return DEFAULT_AGENT