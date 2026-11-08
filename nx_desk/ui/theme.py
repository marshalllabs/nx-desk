from collections.abc import Callable, Collection

from ..schemas.snapshot import ModRow

# Design tokens. Text pairs meet WCAG AA (4.5:1); "border" and "focus" meet 3:1 against bg, field
# and panel, so control edges and the focus ring stay visible. "line" is only for dividers and hovers.
COLORS = {
    "bg": "#1e2125",
    "panel": "#2c3036",
    "field": "#17191c",
    "ink": "#ecebe7",
    "muted": "#a0a29f",
    "line": "#3a3f46",
    "border": "#747a83",
    "focus": "#e8894f",
    "accent": "#e8894f",
    "accent_hover": "#f0a06d",
    "accent_ink": "#1a1208",
    "ok": "#6cc592",
    "bad": "#f2867e",
    "bad_hover": "#f7a59f",
    "miss": "#b79cf0",
    "select": "#4a3826",
    "ok_soft": "#233a2e",
}
# Spacing in px on a 4 px grid: inside controls (xs), between related controls (sm), between groups
# (md), and around a page (lg).
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16}
RADIUS = 4
LIST_COLUMNS = (
    ("game", "Game", 0),
    ("tags", "Genres", 230),
    ("version", "Mod version", 120),
    ("game_version", "Game version", 120),
    ("size", "Size", 90),
    ("status", "Status", 190),
)
# Columns a narrow list hides first, with the table width below which each one goes. The detail
# pane shows the same values, so nothing is lost.
LIST_HIDE_BELOW = {"tags": 900, "game_version": 700, "version": 600}
LIST_SORTABLE = ("game", "size")
# A mod saved on disk stays under Downloaded while it has an update waiting.
# Picking none shows every row; picking several shows rows that match any of them.
STATUS_FILTERS: dict[str, tuple[str, Callable[[ModRow], bool]]] = {
    "new": ("New", lambda item: item.status == "missing"),
    "update": ("Update", lambda item: item.status == "update"),
    "downloaded": ("Downloaded", lambda item: item.status != "missing" and not item.remote),
    "online": ("Online only", lambda item: item.remote),
}


def status_matches(item: ModRow, picked: Collection[str]) -> bool:
    return not picked or any(STATUS_FILTERS[name][1](item) for name in picked)


ROW_COLORS = {"update": "accent", "active": "accent", "ok": "ok", "error": "bad", "missing": "ink"}
