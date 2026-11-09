from typing import Callable, List, Optional, Sequence, Tuple

from pydantic import BaseModel

from .github import RetryState, Transfer
from .snapshot import ModRow


class VersionCells(BaseModel):
    mod: str
    game: str


class TableData(BaseModel):
    columns: Sequence[str]
    rows: Sequence[Sequence[str]]
    total: str = ""


class DownloadChoice(BaseModel):
    label: str
    ids: List[str]


class DownloadChoices(BaseModel):
    download: DownloadChoice
    redownload: DownloadChoice


class GameCells(BaseModel):
    name: str
    tags: Tuple[str, ...]
    mod_version: str
    game_version: str
    size: str
    status: str
    tone: str
    missing: bool
    progress: float


class Preferences(BaseModel):
    font_family: str
    font_size: int
    compression: int
    units: str
    notify: bool
    key: str = ""
    forget: bool = False


class UiCall(BaseModel):
    action: Callable[..., object]
    args: Tuple[object, ...] = ()


class Column(BaseModel):
    key: str
    title: str
    width: int


class RowFilter(BaseModel):
    label: str
    predicate: Callable[[ModRow], bool]

    def matches(self, item: ModRow) -> bool:
        # Callable inputs may be positional-only.
        return self.predicate(item)


class FieldRow(BaseModel):
    key: str
    kind: str
    aliases: List[str]


class InfoField(BaseModel):
    key: str
    value: str
    color: Optional[str] = None


class CompareStamp(BaseModel):
    assets: int
    compared: int
    tag: str


class FolderStamp(BaseModel):
    name: str
    status: str
    progress: str


class ItemProgressStamp(BaseModel):
    key: str
    text: str


class UploadPaintStamp(BaseModel):
    phase: str
    tree: int
    done: int
    message: str
    failed: bool
    runs: int
    alerts: int
    release_list: int
    repo_list: int
    asset_list: int
    folders: List[FolderStamp]
    item_progress: List[ItemProgressStamp]
    transfer: Optional[Transfer]
    compare_list: int
    retry: RetryState


class CatalogOutcome(BaseModel):
    state: str
    message: str
    edited: Optional[str] = None
