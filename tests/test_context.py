"""Tests for kbl.context: system prompt composition."""

from kbl import context, tools


class _Skill:
    def __init__(self, name, description="", skill_tools=None):
        self.name = name
        self.description = description
        self.tools = skill_tools or []


def test_compose_system_full(workspace):
    tool_list = tools.builtin_tools(workspace)
    skills = [
        _Skill("search_wiki", "Find things in the wiki.", []),
        _Skill("weather", "Current weather."),
    ]
    text = context.compose_system(
        "You are KBL.",
        "This wiki covers project X.",
        tool_list,
        skills=skills,
    )
    assert text.startswith("You are KBL.")
    assert "## Workspace\n\nThis wiki covers project X." in text
    assert "## Skills" in text
    assert "- search_wiki: Find things in the wiki." in text
    assert "## Tools" in text
    assert "- list_files: " in text


def test_compose_system_omits_empty_sections():
    text = context.compose_system("You are KBL.", "", None, skills=None)
    assert text == "You are KBL."
    assert "## Workspace" not in text
    assert "## Skills" not in text
    assert "## Tools" not in text


def test_workspace_instructions_default(workspace):
    assert context.workspace_instructions(workspace) == (
        context.DEFAULT_WORKSPACE_INSTRUCTIONS
    )


def test_workspace_instructions_from_file(workspace):
    (workspace / context.INSTRUCTIONS_FILENAME).write_text(
        "  Special rules for this wiki.  "
    )
    assert context.workspace_instructions(workspace) == "Special rules for this wiki."


def test_workspace_instructions_blank_file(workspace):
    (workspace / context.INSTRUCTIONS_FILENAME).write_text("   ")
    assert context.workspace_instructions(workspace) == (
        context.DEFAULT_WORKSPACE_INSTRUCTIONS
    )


def test_skill_gating_lines_with_tools():
    skill = _Skill(
        "search_wiki",
        "Find things.",
        skill_tools=[tools.Tool("find", "finds", {}, lambda: "x")],
    )
    assert context.skill_gating_lines([skill]) == [
        "- search_wiki: Find things.  (tools: find)"
    ]


def test_skill_gating_lines_missing_description():
    assert context.skill_gating_lines([_Skill("bare")]) == [
        "- bare: No description provided."
    ]