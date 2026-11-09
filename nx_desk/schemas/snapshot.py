from typing import List, Optional

from pydantic import BaseModel

from .catalog import Catalog, Mod
from .common import LogEntry
from .download import BatchProgress, Job
from .update import AppUpdate, UpdateJob


# A game as the Catalog tab shows it.
class ModRow(Mod):
    status: str
    remote: bool
    local_version: str
    local_game_version: str
    job: Optional[Job]


class Snapshot(BaseModel):
    items: List[ModRow]
    checked_at: Optional[float]
    checking: bool
    error: Optional[str]
    dir: str
    catalogs: List[Catalog]
    active: Optional[str]
    app_update: Optional[AppUpdate]
    app_update_job: Optional[UpdateJob]
    log: List[LogEntry]
    batch: BatchProgress
