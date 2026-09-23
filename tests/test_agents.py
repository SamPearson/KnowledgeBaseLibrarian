"""Tests for kbl.agents: one directory per agent under the config dir."""

import pytest

from kbl import agents


def test_validate_name_ok():
    assert agents.validate_name("something") == "something"
    assert agents.validate_name(" My Agent 2 ") == "My Agent 2"


def test_validate_name_rejects():
    with pytest.raises(agents.AgentError):
        agents.validate_name("")
    with pytest.raises(agents.AgentError):
        agents.validate_name("a/b")
    with pytest.raises(agents.AgentError):
        agents.validate_name("a!b")


def test_seed_default_creates_assistant(kbl_dirs):
    assert agents.seed_default() is True
    assert (kbl_dirs[0] / "assistant" / agents.PROMPT_FILE).is_file()
    assert agents.seed_default() is False


def test_create_and_get_prompt(kbl_dirs):
    agents.create_agent("helper", prompt="You help.")
    path = kbl_dirs[0] / "helper" / agents.PROMPT_FILE
    assert path.read_text() == "You help.\n"
    assert agents.get_prompt("helper") == "You help.\n"


def test_create_agent_duplicate_raises(kbl_dirs):
    agents.create_agent("helper")
    with pytest.raises(agents.AgentError):
        agents.create_agent("helper")


def test_create_agent_invalid_name(kbl_dirs):
    with pytest.raises(agents.AgentError):
        agents.create_agent("bad/name")


def test_set_prompt_overwrites(kbl_dirs):
    agents.create_agent("helper")
    agents.set_prompt("helper", "New persona.")
    assert agents.get_prompt("helper") == "New persona.\n"


def test_list_agents(kbl_dirs):
    agents.create_agent("beta")
    agents.create_agent("alpha")
    assert agents.list_agents() == ["alpha", "beta"]


def test_rename_agent(kbl_dirs):
    agents.create_agent("oldname")
    agents.rename_agent("oldname", "newname")
    assert agents.list_agents() == ["newname"]
    (kbl_dirs[0] / "oldname").exists() is False


def test_rename_agent_missing_raises(kbl_dirs):
    with pytest.raises(agents.AgentError):
        agents.rename_agent("nope", "new")


def test_rename_agent_to_existing(kbl_dirs):
    agents.create_agent("a")
    agents.create_agent("b")
    with pytest.raises(agents.AgentError):
        agents.rename_agent("a", "b")


def test_delete_agent(kbl_dirs):
    agents.create_agent("temp")
    agents.delete_agent("temp")
    assert agents.list_agents() == [agents.DEFAULT_AGENT]


def test_delete_agent_missing_raises(kbl_dirs):
    with pytest.raises(agents.AgentError):
        agents.delete_agent("nope")


def test_active_agent_prefers_config(kbl_dirs, tmp_config):
    agents.create_agent("primary")
    agents.create_agent("secondary")
    tmp_config.data["active_agent"] = "secondary"
    assert agents.active_agent(tmp_config) == "secondary"


def test_active_agent_falls_back_to_first(kbl_dirs, tmp_config):
    agents.create_agent("zed")
    agents.create_agent("aaa")
    tmp_config.data["active_agent"] = "missing"
    assert agents.active_agent(tmp_config) == "aaa"


def test_active_agent_seeds_default(kbl_dirs, tmp_config):
    tmp_config.data["active_agent"] = "missing"
    assert agents.active_agent(tmp_config) == agents.DEFAULT_AGENT


def test_active_agent_blank_config(kbl_dirs, tmp_config):
    tmp_config.data["active_agent"] = ""
    assert agents.active_agent(tmp_config) == agents.DEFAULT_AGENT


# ---- M4: metadata (agent.json) + AgentRegistry ----

def test_load_agent_defaults_without_metadata(kbl_dirs):
    agents.create_agent("plain")
    agent = agents.load_agent("plain")
    assert agent.id == "plain"
    assert agent.prompt_path == kbl_dirs[0] / "plain" / agents.PROMPT_FILE
    assert agent.description is None
    assert agent.role is None
    assert agent.allowed_tools is None
    assert agent.parent is None
    assert agent.can_delegate_to == []
    assert agent.max_turns == agents.DEFAULT_MAX_TURNS
    assert agent.max_depth == agents.DEFAULT_MAX_DEPTH
    assert not agents.metadata_path("plain").exists()


def test_load_agent_missing_raises(kbl_dirs):
    with pytest.raises(agents.AgentError):
        agents.load_agent("nope")


def test_save_and_reload_metadata(kbl_dirs):
    agents.create_agent("coder")
    agent = agents.load_agent("coder")
    agent.role = "python expert"
    agent.allowed_tools = ["read_file", "search_files"]
    agent.can_delegate_to = ["assistant"]
    agent.max_turns = 12
    agent.max_depth = 2
    agents.save_metadata("coder", agent)

    assert agents.metadata_path("coder").is_file()
    reloaded = agents.load_agent("coder")
    assert reloaded.role == "python expert"
    assert reloaded.allowed_tools == ["read_file", "search_files"]
    assert reloaded.can_delegate_to == ["assistant"]
    assert reloaded.max_turns == 12
    assert reloaded.max_depth == 2
    assert agents.get_prompt("coder") == agents.DEFAULT_SYSTEM_PROMPT + "\n"


def test_save_metadata_does_not_require_prompt_copy(kbl_dirs):
    agents.create_agent("coder")
    metadata = agents.load_agent("coder")
    agents.save_metadata("coder", metadata)
    assert agents.get_prompt("coder").strip()


def test_registry_list_returns_agent_objects(kbl_dirs):
    agents.create_agent("beta")
    agents.create_agent("alpha")
    items = agents.AgentRegistry().list_agents()
    assert [a.id for a in items] == ["alpha", "beta"]
    assert all(isinstance(a, agents.Agent) for a in items)


def test_registry_get(kbl_dirs):
    agents.create_agent("gamma")
    assert agents.AgentRegistry().get("gamma").id == "gamma"


def test_registry_active_matches_active_agent(kbl_dirs, tmp_config):
    agents.create_agent("primary")
    agents.create_agent("secondary")
    tmp_config.data["active_agent"] = "secondary"
    assert agents.AgentRegistry().active(tmp_config) == "secondary"


def test_registry_can_delegate_to_direct(kbl_dirs):
    agents.create_agent("solo")
    solo = agents.load_agent("solo")
    solo.can_delegate_to = ["assistant"]
    agents.save_metadata("solo", solo)
    assert agents.AgentRegistry().can_delegate_to("solo") == ["assistant"]


def test_registry_can_delegate_to_resolves_chain(kbl_dirs):
    agents.create_agent("root")
    agents.create_agent("mid")
    agents.create_agent("leaf")
    mid = agents.load_agent("mid")
    mid.can_delegate_to = ["leaf"]
    agents.save_metadata("mid", mid)
    root = agents.load_agent("root")
    root.can_delegate_to = ["mid"]
    agents.save_metadata("root", root)
    assert agents.AgentRegistry().can_delegate_to("root") == ["mid", "leaf"]


def test_registry_can_delegate_to_is_cycle_safe(kbl_dirs):
    agents.create_agent("cyc_a")
    agents.create_agent("cyc_b")
    a = agents.load_agent("cyc_a")
    a.can_delegate_to = ["cyc_b"]
    agents.save_metadata("cyc_a", a)
    b = agents.load_agent("cyc_b")
    b.can_delegate_to = ["cyc_a"]
    agents.save_metadata("cyc_b", b)
    assert agents.AgentRegistry().can_delegate_to("cyc_a") == ["cyc_b", "cyc_a"]