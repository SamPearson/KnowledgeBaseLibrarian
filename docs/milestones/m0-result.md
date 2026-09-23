# M0 — Test Harness (pure-service test suite)

Status: **complete** (2026-09-22)

## Goal

Establish a green baseline of pure-service tests before any refactoring
(M1 onwards). Nothing here touches Tkinter, the display, or the network.

## Layout

```
pytest.ini                 # testpaths=tests, pythonpath=.
requirements-dev.txt       # -r requirements.txt + pytest
tests/
  conftest.py              # isolated ~/.kbl (tmp), tmp_config, workspace fixtures
  test_agents.py           # agent CRUD, name validation, defaults, active fallback
  test_chat_client.py      # stream content/reasoning, split tool-call assembly,
                           #  stop_event abort, legacy function_call, fetch_models,
                           #  tools schema injection, ServerError wrapping
  test_config.py           # defaults, save/load roundtrip, merge semantics,
                           #  migrations (theme, active_workspace,
                           #  active_conversation), singleton, corrupt fallback
  test_context.py          # compose_system section assembly, instructions source
  test_conversations.py    # workspace_id_for, save/assign/load/rename/list,
                           #  per-workspace scoping, corrupt handling
  test_purity.py           # architecture guard: no tkinter/ttkbootstrap imports
                           #  in the 8 pure-service modules
  test_tools.py            # sandboxing (_within), list/read/search/headings,
                           #  create/edit + backups, run_tool dispatch/errors,
                           #  schemas, gating lines
  test_toolstore.py        # SKILL.md parsing, tools.py import, scan, collect,
                           #  disable gating, sample install, storage ops
  test_workspaces.py       # register/add/remove/set_active/active fallback
```

## Results

- `pytest tests/` → **115 passed** in ~0.4s, headless (no DISPLAY required).
- The `test_purity.py` guard FAILS the build if any pure service imports
  Tkinter or ttkbootstrap — the architecture's pure-services invariant is now
  enforced by CI, not convention.

## Notes

- The Config process-wide singleton is reset in `conftest` (autouse fixture)
  so `Config()` calls inside tests can never touch the real `~/.kbl/config.json`.
- Tests bind modules to isolated temp dirs (`tmp_path`) via the `kbl_dirs`
  fixture, so no test writes to the user's real agents/conversations storage.