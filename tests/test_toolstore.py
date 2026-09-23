"""Tests for kbl.toolstore: skill discovery, tools.py imports, collection."""

import pytest

from kbl import toolstore, tools


def _make_skill(root, name, description="desc", tools_py=""):
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody text.\n",
        encoding="utf-8",
    )
    if tools_py:
        (folder / "tools.py").write_text(tools_py, encoding="utf-8")
    return folder


def test_parse_skill_md():
    text = '---\nname: calc\ndescription: "Does math"\n---\n\n# calc\n\nBody.'
    name, desc, body = toolstore.parse_skill_md(text)
    assert name == "calc"
    assert desc == "Does math"
    assert body == "# calc\n\nBody."


def test_parse_skill_md_no_frontmatter():
    name, desc, body = toolstore.parse_skill_md("# just a header")
    assert name is None
    assert desc == ""
    assert body == "# just a header"


def test_validate_name_rejects():
    for bad in ["", "a/b", "a;b"]:
        with pytest.raises(toolstore.ToolStoreError):
            toolstore.validate_name(bad)


def test_create_skill(kbl_dirs, tmp_path):
    root = tmp_path
    folder = toolstore.create_skill(root, "wiki_tool", description="Search the wiki.")
    assert folder == root / "wiki_tool"
    assert (folder / "SKILL.md").exists()
    name, desc, body = toolstore.parse_skill_md((folder / "SKILL.md").read_text())
    assert name == "wiki_tool"
    assert desc == "Search the wiki."
    assert "Implement `tools.py`" in body


def test_create_skill_duplicate_raises(tmp_path):
    toolstore.create_skill(tmp_path, "tool1")
    with pytest.raises(toolstore.ToolStoreError):
        toolstore.create_skill(tmp_path, "tool1")


def test_delete_skill(tmp_path):
    toolstore.create_skill(tmp_path, "tool1")
    toolstore.delete_skill(tmp_path, "tool1")
    assert not (tmp_path / "tool1").exists()
    with pytest.raises(toolstore.ToolStoreError):
        toolstore.delete_skill(tmp_path, "tool1")


def test_rename_skill(kbl_dirs, tmp_path):
    toolstore.create_skill(tmp_path, "old")
    toolstore.rename_skill(tmp_path, "old", "new")
    assert (tmp_path / "new").is_dir()
    assert not (tmp_path / "old").exists()
    with pytest.raises(toolstore.ToolStoreError):
        toolstore.rename_skill(tmp_path, "does-not-exist", "x")


def test_scan_folder_not_a_skill(tmp_path):
    folder = tmp_path / "plain"
    folder.mkdir()
    assert toolstore.scan_folder(folder, "global") is None


def test_scan_folder_skill_without_tools(tmp_path):
    folder = _make_skill(tmp_path, "basic")
    skill = toolstore.scan_folder(folder, "global")
    assert skill.name == "basic"
    assert skill.source == "global"
    assert skill.description == "desc"
    assert skill.tools == []
    assert skill.error == ""


def test_scan_folder_imports_tools_factory(tmp_path):
    folder = _make_skill(
        tmp_path,
        "math",
        tools_py=(
            "from kbl.tools import Tool\n"
            "def tools():\n"
            "    return [Tool('add', 'Adds.', {'type': 'object', 'properties': {}}, lambda: '1')]\n"
        ),
    )
    skill = toolstore.scan_folder(folder, "workspace")
    assert [t.name for t in skill.tools] == ["add"]


def test_scan_folder_handles_broken_tools_py(tmp_path):
    folder = _make_skill(tmp_path, "broken", tools_py="raise RuntimeError('boom')")
    skill = toolstore.scan_folder(folder, "global")
    assert "boom" in skill.error
    assert skill.tools == []


def test_scan_root_sorted(tmp_path):
    _make_skill(tmp_path, "b_tool")
    _make_skill(tmp_path, "a_tool")
    names = [s.name for s in toolstore.scan_root(tmp_path, "global")]
    assert names == ["a_tool", "b_tool"]


def test_collect_tools_no_workspace(tmp_config):
    col = toolstore.collect_tools(None, tmp_config)
    assert col.enabled_tools == []
    assert col.skills == []


def test_collect_tools_builtin_only(workspace, tmp_config):
    col = toolstore.collect_tools(str(workspace), tmp_config)
    assert [t.name for t in col.enabled_tools] == [t.name for t in tools.builtin_tools(workspace)]


def test_collect_tools_disabled(workspace, tmp_config):
    tmp_config.data["disabled_tools"] = ["read_file"]
    col = toolstore.collect_tools(str(workspace), tmp_config)
    names = [t.name for t in col.enabled_tools]
    assert "read_file" not in names
    assert "list_files" in names


def test_collect_tools_global_and_workspace_skills(workspace, tmp_config, kbl_dirs):
    _make_skill(toolstore.global_root(), "global_tool",
                tools_py=("from kbl.tools import Tool\n"
                          "TOOLS = [Tool('g1', 'd', {'type': 'object', 'properties': {}}, lambda: 'x')]\n"))
    _make_skill(toolstore.workspace_root(workspace), "ws_tool",
                tools_py=("from kbl.tools import Tool\n"
                          "TOOLS = [Tool('w1', 'd', {'type': 'object', 'properties': {}}, lambda: 'y')]\n"))
    col = toolstore.collect_tools(str(workspace), tmp_config)
    names = [t.name for t in col.enabled_tools]
    assert "g1" in names
    assert "w1" in names
    assert {s.name for s in col.all_skills} == {"global_tool", "ws_tool"}


def test_collect_tools_duplicate_warning(workspace, tmp_config):
    _make_skill(toolstore.global_root(), "dup",
                tools_py=("from kbl.tools import Tool\n"
                          "TOOLS = [Tool('read_file', 'd', {'type': 'object', 'properties': {}}, lambda: 'x')]\n"))
    col = toolstore.collect_tools(str(workspace), tmp_config)
    assert any("Duplicate tool name" in w for w in col.warnings)


def test_set_disabled_toggles_and_persists(tmp_config):
    toolstore.set_disabled(tmp_config, "read_file", True)
    assert "read_file" in tmp_config.data["disabled_tools"]
    toolstore.set_disabled(tmp_config, "read_file", False)
    assert "read_file" not in tmp_config.data["disabled_tools"]


def test_install_sample(workspace):
    dst = toolstore.install_sample(toolstore.workspace_root(workspace), "todo")
    assert (dst / "SKILL.md").exists()
    assert (dst / "tools.py").exists()


def test_install_sample_unknown():
    with pytest.raises(toolstore.ToolStoreError):
        toolstore.install_sample(toolstore.sample_dir(), "nope")


def test_install_sample_duplicate(workspace):
    toolstore.install_sample(toolstore.workspace_root(workspace), "todo")
    with pytest.raises(toolstore.ToolStoreError):
        toolstore.install_sample(toolstore.workspace_root(workspace), "todo")