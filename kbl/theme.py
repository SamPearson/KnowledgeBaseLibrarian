"""Application theme using ttkbootstrap for proper runtime theme switching.

ttkbootstrap provides professional themes with full widget styling including
scrollbars, and allows runtime theme changes without Tcl/Tk conflicts.
"""

import tkinter as tk
import tkinter.font as tkfont

try:
    import ttkbootstrap as ttk
    from ttkbootstrap import Style
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    from tkinter import ttk
    TTKBOOTSTRAP_AVAILABLE = False
    Style = None

from kbl.themes import ThemeManager, DEFAULT_THEME

_THEME_MANAGER = ThemeManager()
_STYLE_INSTANCE = None

# Current palette (module-level, updated by apply())
PALETTE = DEFAULT_THEME.copy()

FAMILY = "TkDefaultFont"
MONO_FAMILY = "TkFixedFont"
SIZE = 11

_PREFERRED_SANS = [
    "Noto Sans",
    "Cantarell",
    "DejaVu Sans",
    "Liberation Sans",
    "Helvetica",
]
_PREFERRED_MONO = [
    "Noto Sans Mono",
    "DejaVu Sans Mono",
    "Consolas",
    "Liberation Mono",
    "Courier New",
]


def _first_available(root, preferred, default):
    try:
        families = set(tkfont.families(root))
    except tk.TclError:
        return default
    for name in preferred:
        if name in families:
            return name
    return default


def _palette_to_ttkbootstrap_theme(palette):
    """Convert our palette to ttkbootstrap-compatible theme name.

    We'll map our palettes to the closest ttkbootstrap theme, or create
    a custom theme if needed.
    """
    # Check if it's close to a dark theme
    window_bg = palette.get("window_bg", "#FFFFFF")
    if window_bg.startswith("#2") or window_bg.startswith("#3"):
        # Dark theme - use darkly or superhero
        return "darkly"
    else:
        # Light theme - use flatly or cosmo
        return "flatly"


def apply(root, theme_name="dark"):
    """Apply a theme to the root window by name."""
    global FAMILY, MONO_FAMILY, PALETTE, _STYLE_INSTANCE

    # Reload themes from disk so newly created/edited themes are picked up
    _THEME_MANAGER.refresh()

    # Load theme palette
    palette = _THEME_MANAGER.get_theme(theme_name.strip() if theme_name else theme_name)
    if palette is None:
        palette = DEFAULT_THEME.copy()
    PALETTE = palette

    if TTKBOOTSTRAP_AVAILABLE:
        # Use ttkbootstrap for full theme support
        if _STYLE_INSTANCE is None:
            # Create style instance on first call
            bootstrap_theme = _palette_to_ttkbootstrap_theme(palette)
            _STYLE_INSTANCE = Style(theme=bootstrap_theme)
        else:
            # Change theme at runtime
            bootstrap_theme = _palette_to_ttkbootstrap_theme(palette)
            _STYLE_INSTANCE.theme_use(bootstrap_theme)

        style = _STYLE_INSTANCE
    else:
        # Fallback to regular ttk
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    FAMILY = _first_available(
        root,
        _PREFERRED_SANS,
        tkfont.nametofont("TkDefaultFont").actual("family"),
    )
    MONO_FAMILY = _first_available(
        root,
        _PREFERRED_MONO,
        tkfont.nametofont("TkFixedFont").actual("family"),
    )

    # Apply our custom colors on top of the ttkbootstrap theme
    root.configure(bg=PALETTE["window_bg"])

    # Customize with our palette colors
    style.configure(
        ".",
        background=PALETTE["slate_bg"],
        foreground=PALETTE["chrome_text"],
        font=(FAMILY, SIZE),
    )
    style.configure("TFrame", background=PALETTE["slate_bg"])
    style.configure("TLabel", background=PALETTE["slate_bg"], foreground=PALETTE["chrome_text"])
    style.configure("Dim.TLabel", foreground=PALETTE["chrome_text_dim"])

    style.configure(
        "TButton",
        background=PALETTE["slate_alt"],
        foreground=PALETTE["chrome_text"],
        borderwidth=1,
    )
    style.map(
        "TButton",
        background=[("active", PALETTE["accent"]), ("pressed", PALETTE["accent_hover"])],
        foreground=[("active", PALETTE["accent_text"]), ("pressed", PALETTE["accent_text"])],
    )

    style.configure(
        "Accent.TButton",
        background=PALETTE["accent"],
        foreground=PALETTE["accent_text"],
    )
    style.map(
        "Accent.TButton",
        background=[("active", PALETTE["accent_hover"]), ("pressed", PALETTE["accent_hover"])],
    )

    style.configure(
        "Treeview",
        background=PALETTE["slate_bg"],
        fieldbackground=PALETTE["slate_bg"],
        foreground=PALETTE["chrome_text"],
        rowheight=28,
        bordercolor=PALETTE["border"],
    )
    style.map(
        "Treeview",
        background=[("selected", PALETTE["accent"])],
        foreground=[("selected", PALETTE["accent_text"])],
    )

    style.configure(
        "TPanedwindow",
        background=PALETTE["accent"],
    )

    # ttkbootstrap handles scrollbars automatically with proper theming!
    # But we can still customize them with our colors
    style.configure(
        "Vertical.TScrollbar",
        background=PALETTE["slate_alt"],
        troughcolor=PALETTE["slate_bg"],
        arrowcolor=PALETTE["chrome_text"],
    )
    style.configure(
        "Horizontal.TScrollbar",
        background=PALETTE["slate_alt"],
        troughcolor=PALETTE["slate_bg"],
        arrowcolor=PALETTE["chrome_text"],
    )

    return style


def style_text(widget, bg="parchment", padx=16, pady=12):
    """Style a Text widget with theme colors."""
    widget.configure(
        bg=PALETTE[f"{bg}_bg"],
        fg=PALETTE["ink"],
        font=(FAMILY, SIZE),
        insertbackground=PALETTE["ink"],
        selectbackground=PALETTE["accent"],
        selectforeground=PALETTE["accent_text"],
        padx=padx,
        pady=pady,
        relief="flat",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=PALETTE["border"],
        highlightcolor=PALETTE["accent"],
    )


def style_listbox(widget):
    """Style a Listbox widget with theme colors."""
    widget.configure(
        bg=PALETTE["slate_bg"],
        fg=PALETTE["chrome_text"],
        font=(FAMILY, SIZE),
        selectbackground=PALETTE["accent"],
        selectforeground=PALETTE["accent_text"],
        highlightthickness=0,
        borderwidth=0,
    )


def style_menubar(menubar):
    """Style a menubar with theme colors."""
    menubar.configure(
        bg=PALETTE["slate_bg"],
        fg=PALETTE["chrome_text"],
        activebackground=PALETTE["slate_alt"],
        activeforeground=PALETTE["chrome_text"],
        bd=0,
        relief="flat",
    )


def style_menu(menu):
    """Style a menu with theme colors."""
    menu.configure(
        bg=PALETTE["slate_alt"],
        fg=PALETTE["chrome_text"],
        activebackground=PALETTE["accent"],
        activeforeground=PALETTE["accent_text"],
        disabledforeground=PALETTE["chrome_text_dim"],
        selectcolor=PALETTE["accent_text"],
        bd=1,
        relief="flat",
        tearoff=0,
    )


def get_html_css_overrides():
    """Return CSS rules that override tkhtmlview defaults for the current theme."""
    return f"""
    a {{ color: {PALETTE['accent']}; }}
    code {{ background-color: {PALETTE['slate_alt']}; color: {PALETTE['chrome_text']}; }}
    pre {{ background-color: {PALETTE['slate_alt']}; color: {PALETTE['chrome_text']}; padding: 8px; }}
    blockquote {{ color: {PALETTE['chrome_text_dim']}; border-left: 3px solid {PALETTE['accent']}; padding-left: 12px; }}
    h1, h2, h3, h4, h5, h6 {{ color: {PALETTE['accent']}; }}
    table {{ border-collapse: collapse; }}
    td, th {{ border: 1px solid {PALETTE['border']}; padding: 4px 8px; }}
    """


def get_ttkbootstrap_themes():
    """Return list of available ttkbootstrap themes if available."""
    if not TTKBOOTSTRAP_AVAILABLE:
        return []
    return [
        "darkly", "superhero", "solar", "cyborg", "vapor",  # Dark themes
        "flatly", "cosmo", "litera", "minty", "pulse", "sandstone", "united", "yeti",  # Light themes
    ]