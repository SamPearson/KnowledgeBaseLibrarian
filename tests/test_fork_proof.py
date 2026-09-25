"""M7: fork-proof drop-in checks.

Locks in the Roadmap-M7 acceptance mechanically: swapping the harness
(orchestrate -> StableDiffusionHarness) or the display renderer
(markdown_render -> an image-capable renderer) requires no edits inside
``MainWindow`` or ``kbl/panels/*``. The seams stay as-is; only the wiring
arguments at ``MainWindow._build_panels`` change.
"""

import ast
import pathlib

import kbl
from kbl import contracts

PANELS_DIR = pathlib.Path(kbl.__file__).parent / "panels"
MAIN_WINDOW = pathlib.Path(kbl.__file__).parent / "main_window.py"

FORK_MODULES = ("sd_harness", "image_render")
FORBIDDEN_IMPORTS = tuple(name for m in FORK_MODULES for name in (f"kbl.{m}", m))


def _imported_names(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
    return names


def _view_files():
    yield MAIN_WINDOW
    yield from sorted(PANELS_DIR.glob("*.py"))


def test_panels_and_main_window_never_import_fork_modules():
    for path in _view_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            assert name not in FORBIDDEN_IMPORTS, f"{path.name} imports {name}"


def test_swap_sites_are_the_documented_wiring_arguments():
    main = MAIN_WINDOW.read_text(encoding="utf-8")
    assert "harness=harness.orchestrate" in main
    assert "renderer=renderer" in main

    chat = (PANELS_DIR / "chat.py").read_text(encoding="utf-8")
    assert "harness=None" in chat
    assert "renderer=None" in chat


def test_harness_drop_in_satisfies_the_contract():
    from kbl.sd_harness import StableDiffusionHarness

    assert isinstance(StableDiffusionHarness(), contracts.Harness)


def test_image_renderer_drop_in_satisfies_the_contract():
    from kbl.image_render import TkImageRenderer

    assert isinstance(TkImageRenderer(), contracts.ImageRenderer)