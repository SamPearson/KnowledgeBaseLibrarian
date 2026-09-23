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