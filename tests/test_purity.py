"""Architecture guard: pure services must never import Tkinter.

This is the M0 analogue of the 'pure services' invariant from the architecture
doc: if a service module ever imports Tkinter, the test suite fails, because
service code that depends on the GUI can no longer be tested headlessly.
"""

import ast
import pathlib

import kbl

PURE_SERVICES = [
    "agents",
    "chat_client",
    "config",
    "context",
    "contracts",
    "conversations",
    "delegator",
    "events",
    "harness",
    "tools",
    "toolstore",
    "workspaces",
]


def _imported_names(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def test_pure_services_have_no_tkinter_import():
    root = pathlib.Path(kbl.__file__).parent
    for module in PURE_SERVICES:
        path = root / f"{module}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert "tkinter" not in _imported_names(tree), f"{module}.py imports tkinter"
        assert "ttkbootstrap" not in _imported_names(tree), f"{module}.py imports ttkbootstrap"