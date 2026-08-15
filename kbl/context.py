"""System message composition for chat requests.

The system message is assembled per request from three sources:

1. The agent's system prompt (behavior/tone/persona).
2. Workspace instructions (domain — what this wiki holds, how to use it).
3. Tool gating lines (what tools exist, appended last).

Workspace instructions come from ``instructions.md`` in the workspace root if
present, otherwise a default describing the workspace as a markdown wiki.
"""

from pathlib import Path

from kbl import tools

INSTRUCTIONS_FILENAME = "instructions.md"

DEFAULT_WORKSPACE_INSTRUCTIONS = (
    "This is a markdown knowledge base (a wiki). Files are plain markdown and "
    "each file documents something specific. You have tools to list, search, "
    "inspect, and read these files. Prefer consulting the wiki over guessing: "
    "narrow down with list_files/search_files/get_headings, then read the "
    "relevant file for its full contents."
)


def workspace_instructions(workspace):
    """Instructions text for a workspace, from its instructions.md or default."""
    if not workspace:
        return DEFAULT_WORKSPACE_INSTRUCTIONS
    path = Path(workspace) / INSTRUCTIONS_FILENAME
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            text = ""
        if text:
            return text
    return DEFAULT_WORKSPACE_INSTRUCTIONS


def compose_system(agent_prompt, workspace_text, tool_list):
    """Assemble the system message: agent prompt + workspace + tool gating."""
    sections = [agent_prompt.strip()]

    if workspace_text and workspace_text.strip():
        sections.append(f"## Workspace\n\n{workspace_text.strip()}")

    if tool_list:
        gating = tools.tool_gating_lines(tool_list)
        sections.append(
            "## Tools\n\n"
            "You have access to these tools on the active workspace. Use them "
            "to consult the wiki instead of inventing contents:\n\n"
            + "\n".join(gating)
            + "\n\n"
            "You can call several tools in one response when a question needs "
            "multiple lookups. Call get_current_date to resolve relative dates "
            "like 'tomorrow' or 'next week'."
        )

    return "\n\n".join(sections)
