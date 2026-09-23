"""Tests for kbl.tools: built-in wiki tools, path sandboxing, run_tool dispatch."""

import pytest

from kbl import tools


def test_list_md_files_excludes_tools_hidden_nonmd(workspace):
    names = tools.list_md_files(workspace)
    assert names == ["a.md", "sub/b.md"]


def test_list_md_files_empty(tmp_path):
    assert tools.list_md_files(tmp_path) == []


def test_within_ok(workspace):
    assert tools._within(workspace, "sub/b.md") == workspace / "sub" / "b.md"


def test_within_escape_rejected(workspace):
    with pytest.raises(tools.ToolError, match="escapes the workspace"):
        tools._within(workspace, "../../outside.md")


def test_read_file(workspace):
    assert tools._read_file(workspace, "a.md").startswith("# A")


def test_read_file_missing(workspace):
    with pytest.raises(tools.ToolError, match="No such file"):
        tools._read_file(workspace, "nope.md")


def test_search_files_line_reference(workspace):
    result = tools._search_files(workspace, "hello")
    assert result == "a.md:2: Hello world"


def test_search_files_no_matches(workspace):
    assert tools._search_files(workspace, "zzz") == (
        "No matches for 'zzz' in the workspace."
    )


def test_search_files_excludes_tools_dir(workspace):
    assert tools._search_files(workspace, "tool content") == (
        "No matches for 'tool content' in the workspace."
    )


def test_search_files_empty_query(workspace):
    with pytest.raises(tools.ToolError, match="non-empty query"):
        tools._search_files(workspace, "   ")


def test_get_headings(workspace):
    assert tools._get_headings(workspace, "a.md") == "# A"
    assert tools._get_headings(workspace, "sub/b.md") == "## B"


def test_get_headings_none(workspace):
    (workspace / "plain.md").write_text("no headings here")
    assert tools._get_headings(workspace, "plain.md") == "(no headings in plain.md)"


def test_get_current_date(workspace):
    result = tools._get_current_date()
    assert "UTC" in result
    assert result.count(" ") >= 2


def test_create_file_creates_with_md_suffix(workspace):
    out = tools._create_file(workspace, "notes/new")
    assert out == "Created notes/new.md"
    assert (workspace / "notes" / "new.md").read_text() == ""


def test_create_file_existing_raises(workspace):
    with pytest.raises(tools.ToolError, match="already exists"):
        tools._create_file(workspace, "a.md")


def test_edit_file_writes_and_backs_up(workspace):
    out = tools._edit_file(workspace, "a.md", "# A edited")
    assert out.startswith("File updated and backed up to backups/a.")
    assert (workspace / "a.md").read_text() == "# A edited"
    backups = list((workspace / "backups").glob("a.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "# A\nHello world\n"


def test_edit_file_empty_content_rejected(workspace):
    with pytest.raises(tools.ToolError, match="cannot be empty"):
        tools._edit_file(workspace, "a.md", "   ")


def test_edit_file_missing_raises(workspace):
    with pytest.raises(tools.ToolError, match="No such file"):
        tools._edit_file(workspace, "nope.md", "x")


def test_builtin_tools_schema(workspace):
    builtin = tools.builtin_tools(workspace)
    assert [t.name for t in builtin] == [
        "list_files",
        "read_file",
        "search_files",
        "get_headings",
        "get_current_date",
        "create_file",
        "edit_file",
    ]
    schema = builtin[1].to_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "read_file"
    assert schema["function"]["parameters"]["required"] == ["path"]


def test_run_tool_found_and_returns(workspace):
    builtin = tools.builtin_tools(workspace)
    assert tools.run_tool(builtin, "read_file", {"path": "a.md"}).startswith("# A")


def test_run_tool_string_arguments(workspace):
    builtin = tools.builtin_tools(workspace)
    out = tools.run_tool(builtin, "read_file", '{"path": "a.md"}')
    assert out.startswith("# A")


def test_run_tool_unknown(workspace):
    assert tools.run_tool(tools.builtin_tools(workspace), "nope", {}) == (
        "Unknown tool: nope"
    )


def test_run_tool_bad_json(workspace):
    out = tools.run_tool(tools.builtin_tools(workspace), "read_file", "{oops")
    assert out.startswith("Could not parse arguments for read_file")


def test_run_tool_type_error(workspace):
    out = tools.run_tool(tools.builtin_tools(workspace), "read_file", {})
    assert out.startswith("Bad arguments for read_file")


def test_run_tool_tool_error_message(workspace):
    out = tools.run_tool(
        tools.builtin_tools(workspace), "read_file", {"path": "missing.md"}
    )
    assert out == "No such file: missing.md"


def test_run_tool_generic_exception(workspace):
    boom = tools.Tool(
        name="boom",
        description="boom",
        parameters={},
        func=lambda: (_ for _ in ()).throw(ValueError("kaput")),
    )
    assert tools.run_tool([boom], "boom", {}) == "boom failed: kaput"


def test_tool_gating_lines(workspace):
    lines = tools.tool_gating_lines(tools.builtin_tools(workspace))
    assert lines[0].startswith("- list_files: ")
    assert "- read_file(path): " in lines[1]
    assert "- create_file(path, content?): " in lines[5]