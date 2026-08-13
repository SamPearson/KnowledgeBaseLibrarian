"""Theme management: define, save, load, and apply themes."""

import copy
import json
from pathlib import Path
from typing import Dict, Optional

CONFIG_DIR = Path.home() / ".kbl"
THEMES_DIR = CONFIG_DIR / "themes"

# Default theme palette (dark)
DEFAULT_THEME = {
    "window_bg": "#23282E",
    "slate_bg": "#2F3842",
    "slate_alt": "#39444F",
    "border": "#1B2026",
    "chrome_text": "#E6E1D3",
    "chrome_text_dim": "#A6A191",
    "parchment_bg": "#23282E",
    "parchment_alt": "#2F3842",
    "ink": "#E6E1D3",
    "ink_soft": "#A6A191",
    "accent": "#3F7D4C",
    "accent_hover": "#4C8F5A",
    "accent_text": "#F4F0E6",
}

# Light theme
LIGHT_THEME = {
    "window_bg": "#FFFFFF",
    "slate_bg": "#F5F5F5",
    "slate_alt": "#EEEEEE",
    "border": "#DDDDDD",
    "chrome_text": "#333333",
    "chrome_text_dim": "#666666",
    "parchment_bg": "#FFFFFF",
    "parchment_alt": "#F8F8F8",
    "ink": "#000000",
    "ink_soft": "#555555",
    "accent": "#0066CC",
    "accent_hover": "#0052A3",
    "accent_text": "#FFFFFF",
}

BUILTIN_THEMES = {
    "dark": DEFAULT_THEME,
    "light": LIGHT_THEME,
}

# Old names still referenced by existing config files
_LEGACY_ALIASES = {"default": "dark"}


class ThemeManager:
    """Manage theme loading, saving, and listing."""

    def __init__(self):
        self._custom_themes: Dict[str, Dict[str, str]] = {}
        self._load_custom_themes()
        self._ensure_examples_exist()

    def _load_custom_themes(self):
        """Load all custom themes from disk."""
        self._custom_themes.clear()
        if not THEMES_DIR.exists():
            return
        for theme_file in THEMES_DIR.glob("*.json"):
            try:
                theme_data = json.loads(theme_file.read_text(encoding="utf-8"))
                name = theme_file.stem
                # Skip example files
                if not name.startswith("example-"):
                    self._custom_themes[name] = theme_data
            except (json.JSONDecodeError, OSError):
                pass

    def _ensure_examples_exist(self):
        """Create example theme files if they don't exist."""
        THEMES_DIR.mkdir(parents=True, exist_ok=True)

        readme_path = THEMES_DIR / "README.md"
        if not readme_path.exists():
            readme_path.write_text(_THEMES_README, encoding="utf-8")

        examples = {
            "example-warm.json": _WARM_THEME,
            "example-solarized-dark.json": _SOLARIZED_DARK_THEME,
            "example-nord.json": _NORD_THEME,
            "example-dracula.json": _DRACULA_THEME,
        }

        for filename, theme_data in examples.items():
            path = THEMES_DIR / filename
            if not path.exists():
                path.write_text(
                    json.dumps(theme_data, indent=2) + "\n",
                    encoding="utf-8",
                )

    def refresh(self):
        """Reload custom themes from disk (picks up new/edited/deleted files)."""
        self._load_custom_themes()

    @staticmethod
    def _normalize(name: str) -> str:
        """Map legacy theme names to their current equivalents."""
        return _LEGACY_ALIASES.get(name, name)

    def get_theme(self, name: str) -> Optional[Dict[str, str]]:
        """Get a theme by name (builtin or custom)."""
        name = self._normalize(name)
        if name in BUILTIN_THEMES:
            return copy.deepcopy(BUILTIN_THEMES[name])
        if name in self._custom_themes:
            return copy.deepcopy(self._custom_themes[name])
        return None

    def list_themes(self) -> list:
        """Return a sorted list of all theme names (builtin + custom)."""
        return sorted(list(BUILTIN_THEMES.keys()) + list(self._custom_themes.keys()))

    def save_theme(self, name: str, palette: Dict[str, str]) -> bool:
        """Save a custom theme to disk."""
        if self._normalize(name) in BUILTIN_THEMES:
            return False  # Can't overwrite builtin themes
        try:
            THEMES_DIR.mkdir(parents=True, exist_ok=True)
            theme_file = THEMES_DIR / f"{name}.json"
            theme_file.write_text(
                json.dumps(palette, indent=2) + "\n",
                encoding="utf-8",
            )
            self._custom_themes[name] = copy.deepcopy(palette)
            return True
        except OSError:
            return False

    def delete_theme(self, name: str) -> bool:
        """Delete a custom theme."""
        if self._normalize(name) in BUILTIN_THEMES:
            return False  # Can't delete builtin themes
        if name not in self._custom_themes:
            return False
        try:
            theme_file = THEMES_DIR / f"{name}.json"
            if theme_file.exists():
                theme_file.unlink()
            del self._custom_themes[name]
            return True
        except OSError:
            return False

    def is_builtin(self, name: str) -> bool:
        """Check if a theme is builtin (read-only)."""
        return self._normalize(name) in BUILTIN_THEMES

    def is_custom(self, name: str) -> bool:
        """Check if a theme is custom."""
        return name in self._custom_themes


# Example themes

_THEMES_README = """# Custom Themes

This folder contains custom theme definitions for the Knowledge Base Librarian.

The app uses **ttkbootstrap** for professional widget theming. Your custom color
palettes are layered on top of ttkbootstrap's base themes.

## Creating a Custom Theme

1. Create a new file with a `.json` extension (e.g., `my-theme.json`)
2. Copy the structure from one of the example theme files below
3. Edit the hex color values to your liking
4. Save the file
5. Restart the app or use Theme > Select Theme to load it

## Theme Color Fields

Each theme JSON file must define these 13 colors:

- **window_bg** — Main window background
- **slate_bg** — Panel and chrome background (main UI surfaces)
- **slate_alt** — Alternate panel background (buttons, tabs, etc.)
- **border** — Border and divider colors
- **chrome_text** — Text on panel backgrounds
- **chrome_text_dim** — Dimmed text (secondary labels)
- **parchment_bg** — Editor/reader background (reading surfaces)
- **parchment_alt** — Alternate editor background (code blocks, blockquotes)
- **ink** — Text on reading surfaces (primary)
- **ink_soft** — Text on reading surfaces (secondary)
- **accent** — Primary accent color (buttons, highlights, links)
- **accent_hover** — Accent color when hovered
- **accent_text** — Text on accent backgrounds

## Example Structure

```json
{
  "window_bg": "#23282E",
  "slate_bg": "#2F3842",
  "slate_alt": "#39444F",
  "border": "#1B2026",
  "chrome_text": "#E6E1D3",
  "chrome_text_dim": "#A6A191",
  "parchment_bg": "#F4EEE0",
  "parchment_alt": "#E9E1CD",
  "ink": "#3A3530",
  "ink_soft": "#6E675C",
  "accent": "#3F7D4C",
  "accent_hover": "#4C8F5A",
  "accent_text": "#F4F0E6"
}
```

Builtin Themes
The app includes two builtin themes:
dark — Dark theme with parchment reading surfaces (read-only)
light — Light theme (read-only)
Builtin themes cannot be edited or deleted.
Note on ttkbootstrap
The app automatically selects an appropriate ttkbootstrap base theme based on your custom colors (dark themes use "darkly", light themes use "flatly"). Your custom colors are then applied on top for a cohesive look. 

"""

_WARM_THEME = { "window_bg": "#3A2F2F", "slate_bg": "#4A3E3E", "slate_alt": "#5A4E4E", "border": "#2A1F1F", "chrome_text": "#E8D5C4", "chrome_text_dim": "#A89080", "parchment_bg": "#3A2F2F", "parchment_alt": "#4A3E3E", "ink": "#E8D5C4", "ink_soft": "#A89080", "accent": "#D97E3A", "accent_hover": "#E89A52", "accent_text": "#FFFAF5", }
_SOLARIZED_DARK_THEME = { "window_bg": "#002B36", "slate_bg": "#073642", "slate_alt": "#586E75", "border": "#002B36", "chrome_text": "#93A1A1", "chrome_text_dim": "#657B83", "parchment_bg": "#002B36", "parchment_alt": "#073642", "ink": "#93A1A1", "ink_soft": "#657B83", "accent": "#268BD2", "accent_hover": "#2AA198", "accent_text": "#FDF6E3", }
_NORD_THEME = { "window_bg": "#2E3440", "slate_bg": "#3B4252", "slate_alt": "#434C5E", "border": "#2E3440", "chrome_text": "#ECEFF4", "chrome_text_dim": "#D8DEE9", "parchment_bg": "#2E3440", "parchment_alt": "#3B4252", "ink": "#ECEFF4", "ink_soft": "#D8DEE9", "accent": "#88C0D0", "accent_hover": "#81A1C1", "accent_text": "#2E3440", }
_DRACULA_THEME = { "window_bg": "#282A36", "slate_bg": "#383A59", "slate_alt": "#44475A", "border": "#1E1F29", "chrome_text": "#F8F8F2", "chrome_text_dim": "#6272A4", "parchment_bg": "#282A36", "parchment_alt": "#383A59", "ink": "#F8F8F2", "ink_soft": "#6272A4", "accent": "#BD93F9", "accent_hover": "#FF79C6", "accent_text": "#F8F8F2", }


