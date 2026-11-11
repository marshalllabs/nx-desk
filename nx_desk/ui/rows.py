from typing import Dict, Iterable, List, Sequence, Tuple

from ..config import MISSING_VERSION
from ..names import display_version
from ..schemas.github import CompareRow
from ..schemas.presentation import DownloadChoice, DownloadChoices, TableData, VersionCells
from ..schemas.snapshot import ModRow
from ..utils.sizes import format_size

# Parts of the UI that need no toolkit, so the tests can reach them.


class SortState:
    def __init__(self, column: str) -> None:
        self.column = column
        self.ascending = True

    def toggle(self, column: str) -> None:
        self.ascending = column != self.column or not self.ascending
        self.column = column

    def choose(self, column: str) -> None:
        self.column = column

    def set_direction(self, ascending: bool) -> None:
        self.ascending = ascending

    def title(self, column: str, text: str) -> str:
        if column != self.column:
            return text

        return f"{text} {'▲' if self.ascending else '▼'}"


def status_text(item: ModRow) -> str:
    job = item.job

    if job:
        if job.phase == "error":
            return "Error"

        zipped = job.zipped
        sent = job.sent

        if job.phase == "zipping" and zipped and job.total:
            return f"Zipping {100 * zipped / job.total:.0f}%"

        if job.phase == "uploading" and sent and job.total:
            speed = f" · {format_size(value=job.speed)}/s" if job.speed else ""

            return f"Uploading {100 * sent / job.total:.0f}%{speed}"

        if job.phase == "downloading":
            speed = f" · {format_size(value=job.speed)}/s" if job.speed else ""

            if job.total:
                return f"{100 * job.done / job.total:.0f}%{speed}"

            return f"{format_size(value=job.done)}{speed}"  # size unknown: show bytes pulled so far

        return {
            "queued": "Queued",
            "verifying": "Verifying",
            "waiting_limit": "Waiting for the server",
            "waiting_repack": "Waiting to repack",
            "repacking": "Repacking",
            "waiting_upload": "Waiting to upload",
            "zipping": "Zipping",
            "uploading": "Uploading",
            "recording": "Updating state.json",
            "deleting": "Deleting local copy",
        }[job.phase]

    if item.source_failures:
        return "Source failed (paused)" if item.source_failures >= 3 else f"Source failed ({item.source_failures}/3)"

    if item.status == "update":
        return "Update available"

    if item.status == "ok":
        return "Online only" if item.remote else "Downloaded"

    return "Not downloaded"


# A pending update shows the old value beside the new one, in the column that changes.
def changed(old: str, new: str) -> str:
    return f"{old} → {new}" if old and old != new else new


def version_cells(item: ModRow) -> VersionCells:
    mod = item.version or "-"
    game = display_version(game_version=item.game_version)
    shown_game = "Miss" if game == MISSING_VERSION else game

    if item.status != "update" or item.job:
        return VersionCells(mod=mod, game=shown_game)

    old_game = display_version(game_version=item.local_game_version)
    old_game = "" if old_game == MISSING_VERSION else old_game

    return VersionCells(mod=changed(old=item.local_version, new=mod), game=changed(old=old_game, new=shown_game))


def update_text(item: ModRow) -> str:
    versions = version_cells(item=item)
    mod = versions.mod
    game = versions.game
    parts = [f"mod {mod}" if "→" in mod else "", f"game {game}" if "→" in game else ""]
    found = ", ".join(part for part in parts if part)

    return f"Update available: {found}" if found else "Update available"


MOD_COLUMNS: Tuple[str, ...] = ("Game", "Mod version", "Game version", "Size")


# The rows a download or update question lists; an update shows old → new versions.
def mod_rows(items: Iterable[ModRow]) -> TableData:
    rows: List[Tuple[str, ...]] = [
        (
            item.name,
            version_cells(item=item).mod,
            version_cells(item=item).game,
            format_size(value=item.size) if item.size else "-",
        )
        for item in items
    ]
    total = sum(item.size or 0 for item in items)

    return TableData(columns=MOD_COLUMNS, rows=rows, total=total_text(size=total))


def total_text(size: int) -> str:
    return f"Total {format_size(value=size)}" if size else ""


# How far the download or upload of a row has come, from 0 to 1; negative when none runs.
def progress_of(item: ModRow) -> float:
    job = item.job

    if job and job.phase == "downloading" and job.total:
        return min(1.0, job.done / job.total)

    if job and job.phase == "uploading" and job.total:
        return min(1.0, job.sent / job.total)

    return -1.0


def row_tag(item: ModRow) -> str:
    job = item.job

    if job:
        return "error" if job.phase == "error" else "active"

    return "error" if item.source_failures else item.status


# A filter button names its one pick, or counts several.
def picked_text(title: str, picked: Sequence[str]) -> str:
    if not picked:
        return title

    return f"{title}: {picked[0]}" if len(picked) == 1 else f"{title} ({len(picked)})"


def format_time(seconds: float) -> str:
    minutes, rest = divmod(round(number=seconds), 60)
    hours, minutes = divmod(minutes, 60)

    return f"{hours}h {minutes}m" if hours else f"{minutes}m {rest}s" if minutes else f"{rest}s"


# Repositories show by name alone, unless two owners have one of the same name.
def repo_labels(repos: Iterable[str]) -> Dict[str, str]:
    repos = list(repos)
    names = [repo.split(sep="/", maxsplit=1)[-1] for repo in repos]

    return {repo: name for repo, name in zip(repos, names, strict=True) if names.count(name) == 1}


def release_labels(latest: str) -> Dict[str, str]:
    return {latest: f"{latest}  (latest)"} if latest else {}


# The states of a release file while two releases are compared: legend text and color.
COMPARE_STATES = {"same": ("On both", "ok"), "differs": ("Other version", "accent"), "only": ("Only here", "miss")}


def compare_status(row: CompareRow) -> str:
    if row.state == "differs":
        return "Other version: " + ", ".join(row.other)

    return COMPARE_STATES[row.state][0]


# Rows of the GitHub tab that are waiting rather than at work.
WAITING = ("Queued", "Waiting to upload")
UPLOAD_STATUS = {
    "uploaded": "Uploaded",
    "missing": "Not uploaded",
    "done": "Uploaded",
    "error": "Failed",
    "working": "Working",
    "fresh": "Downloaded",
}


# The Catalog tab's two download buttons, each a label and the mods it takes. While no game or just one is picked
# they take the whole catalog ("Download all" the new mods, "Re-download all" the downloaded ones); with several
# picked they take those ("... selected").
def download_scopes(
    picked: int,
    new: List[str],
    done: List[str],
    picked_new: List[str],
    picked_done: List[str],
) -> DownloadChoices:
    if picked > 1:
        return DownloadChoices(
            download=DownloadChoice(label="Download selected", ids=picked_new),
            redownload=DownloadChoice(label="Re-download selected", ids=picked_done),
        )

    return DownloadChoices(
        download=DownloadChoice(label="Download all", ids=new),
        redownload=DownloadChoice(label="Re-download all", ids=done),
    )


# One label for every transfer button in both tabs: "Download (4 · 120 MiB)". A part that is 0 is left out.
def action_text(text: str, count: int, size: int = 0) -> str:
    parts = [f"{count:,}"] if count else []

    if size:
        parts.append(format_size(value=size))

    return f"{text} ({' · '.join(parts)})" if parts else text
