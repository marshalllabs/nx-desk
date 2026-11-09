import threading
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .catalog import Mod

Outcome = Literal["saved", "failed", "cancelled", "uploaded", "upload_failed", "deleted"]


# One download from queued until saved, and its upload when that follows.
class Job(BaseModel):
    # Updated field by field while it runs, so each change is checked too.
    model_config = ConfigDict(validate_assignment=True)

    phase: str
    done: int
    total: int
    speed: float
    game: str
    # Bytes this job counts for in the batch: twice the size when it is also uploaded.
    weight: int
    message: str = ""
    sent: int = 0
    zipped: int = 0


# Counts of one run of downloads, from the first queued while idle until all have ended.
class Batch(BaseModel):
    # Updated field by field while it runs, so each change is checked too.
    model_config = ConfigDict(validate_assignment=True)

    count: int = 0
    finished: int = 0
    total: int = 0
    passed: int = 0
    saved: int = 0
    failed: int = 0
    cancelled: int = 0
    uploaded: int = 0
    upload_failed: int = 0
    deleted: int = 0


class BatchProgress(BaseModel):
    active: bool
    number: int
    count: int
    finished: int
    saved: int
    failed: int
    cancelled: int
    uploaded: int
    upload_failed: int
    deleted: int
    fraction: float


# How far a download got, for its speed and the log lines every 10%.
class Pace(BaseModel):
    time: float
    done: int
    started: float
    # Bytes already there when this run started, from an earlier partial download.
    start: int
    mark: int


# The file a download produced, before it is repacked.
class Fetched(BaseModel):
    wire: Path


class PriorityTask(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    priority: int
    order: int

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PriorityTask):
            return NotImplemented

        if self.priority != other.priority:
            return self.priority < other.priority

        return self.order < other.order


class DownloadTask(PriorityTask):
    entry: Mod
    cancel: threading.Event


class RepackTask(DownloadTask):
    fetched: Fetched
    target: Path
    started: float


class TransferMark(BaseModel):
    time: float
    done: int


class FetchProgress(BaseModel):
    done: int
    total: int
    partial: bool
