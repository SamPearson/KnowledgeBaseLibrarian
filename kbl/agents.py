"""Agent identities: one directory per agent under ~/.kbl/agents.

Each agent is a directory containing a ``system_prompt.md`` file that is sent
as the system message on every turn, plus an optional ``agent.json`` metadata
file (M4). Users can create, edit, delete, and switch between agents at any
time.

Metadata (agent.json) is optional and backward compatible: an agent without
one behaves exactly as before — it can use every enabled tool, has no role or
parent, and may not delegate to anyone.
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from kbl.config import CONFIG_DIR

AGENTS_DIR = CONFIG_DIR / "agents"
PROMPT_FILE = "system_prompt.md"
METADATA_FILE = "agent.json"
DEFAULT_AGENT = "assistant"
DEFAULT_SYSTEM_PROMPT = (
    "You are KBL, a helpful assistant running on the user's homelab."
)
DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_DEPTH = 1

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


def metadata_path(name):
    """Path to an agent's optional agent.json metadata file."""
    return agent_dir(name) / METADATA_FILE


@dataclass
class Agent:
    """One assistant identity and its metadata.

    Satisfies the M4 ``contracts.Agent`` protocol: ``allowed_tools is None``
    means every currently enabled tool is available.
    """

    id: str
    prompt_path: Path
    description: str | None = None
    role: str | None = None
    allowed_tools: list[str] | None = None
    parent: str | None = None
    can_delegate_to: list[str] = field(default_factory=list)
    max_turns: int = DEFAULT_MAX_TURNS
    max_depth: int = DEFAULT_MAX_DEPTH


def _load_metadata(name):
    """Read an agent's agent.json as a dict (empty when absent/corrupt)."""
    path = metadata_path(name)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load_agent(name):
    """Load one agent as an Agent object, defaulting absent metadata."""
    name = validate_name(name)
    path = prompt_path(name)
    if not path.is_file():
        raise AgentError(f"Agent {name!r} has no system prompt.")
    data = _load_metadata(name)
    allowed = data.get("allowed_tools")
    if isinstance(allowed, list) and all(isinstance(x, str) for x in allowed):
        allowed = list(allowed)
    else:
        allowed = None
    delegable = data.get("can_delegate_to")
    if not isinstance(delegable, list):
        delegable = []
    return Agent(
        id=name,
        prompt_path=path,
        description=data.get("description"),
        role=data.get("role"),
        allowed_tools=allowed,
        parent=data.get("parent"),
        can_delegate_to=[x for x in delegable if isinstance(x, str)],
        max_turns=int(data.get("max_turns") or DEFAULT_MAX_TURNS),
        max_depth=int(data.get("max_depth") or DEFAULT_MAX_DEPTH),
    )


def save_metadata(name, agent):
    """Persist an agent's metadata to agent.json (never touches the prompt)."""
    name = validate_name(name)
    data = {
        "description": agent.description,
        "role": agent.role,
        "allowed_tools": agent.allowed_tools,
        "parent": agent.parent,
        "can_delegate_to": list(agent.can_delegate_to or []),
        "max_turns": agent.max_turns,
        "max_depth": agent.max_depth,
    }
    metadata_path(name).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


class AgentRegistry:
    """M4 standing implementation of contracts.AgentRegistry (kbl.agents).

    Lists/loads agent metadata and resolves which agents may delegate to whom.
    """

    def list_agents(self):
        return [load_agent(name) for name in list_agents()]

    def get(self, agent_id):
        return load_agent(agent_id)

    def active(self, config):
        return active_agent(config)

    def can_delegate_to(self, agent_id):
        """Directly delegable agents, resolved through the delegation graph.

        An agent may delegate to anyone in its own ``can_delegate_to``,
        transitively through the chain (cycle-safe). Delegation is opt-in:
        default/existing agents resolve to an empty list.
        """
        seen = set()
        queue = list(load_agent(agent_id).can_delegate_to or [])
        result = []
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            result.append(current)
            try:
                child = load_agent(current)
            except AgentError:
                continue
            queue.extend(c for c in child.can_delegate_to if c not in seen)
        return result