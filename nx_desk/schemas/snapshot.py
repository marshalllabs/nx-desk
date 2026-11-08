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
    job: Job | None


class Snapshot(BaseModel):
    items: list[ModRow]
    checked_at: float | None
    checking: bool
    error: str | None
    dir: str
    catalogs: list[Catalog]
    active: str | None
    app_update: AppUpdate | None
    app_update_job: UpdateJob | None
    log: list[LogEntry]
    batch: BatchProgress
