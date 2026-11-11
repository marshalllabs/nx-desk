from typing import Collection, Dict, Tuple

from ..schemas.presentation import Column, RowFilter
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
LIST_COLUMNS: Tuple[Column, ...] = (
    Column(key="game", title="Game", width=0),
    Column(key="tags", title="Genres", width=230),
    Column(key="version", title="Mod version", width=120),
    Column(key="game_version", title="Game version", width=120),
    Column(key="size", title="Size", width=90),
    Column(key="status", title="Status", width=190),
)
# Columns a narrow list hides first, with the table width below which each one goes. The detail
# pane shows the same values, so nothing is lost.
LIST_HIDE_BELOW = {"tags": 900, "game_version": 700, "version": 600}
LIST_SORTABLE = ("game", "size")
# A mod saved on disk stays under Downloaded while it has an update waiting.
# Picking none shows every row; picking several shows rows that match any of them.
STATUS_FILTERS: Dict[str, RowFilter] = {
    "new": RowFilter(label="New", predicate=lambda item: item.status == "missing"),
    "update": RowFilter(label="Update", predicate=lambda item: item.status == "update"),
    "downloaded": RowFilter(label="Downloaded", predicate=lambda item: item.status != "missing" and (not item.remote)),
    "failed": RowFilter(label="Source failed", predicate=lambda item: item.source_failures > 0),
    "online": RowFilter(label="Online only", predicate=lambda item: item.remote),
}


def status_matches(item: ModRow, picked: Collection[str]) -> bool:
    return not picked or any(STATUS_FILTERS[name].matches(item=item) for name in picked)


ROW_COLORS = {"update": "accent", "active": "accent", "ok": "ok", "error": "bad", "missing": "ink"}
