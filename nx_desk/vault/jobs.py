import threading
from typing import List

from ..schemas.download import BatchProgress, Job, Outcome
from .base import VaultBase


class Jobs(VaultBase):
    def busy(self) -> bool:
        with self.lock:
            return any(job.phase != "error" for job in self.jobs.values())

    def snapshot_jobs(self) -> List[Job]:
        with self.lock:
            return list(self.jobs.values())

    # A stopped run must not touch a later run of the same mod, so its event is checked first.
    def _update_job(self, entry_id: str, cancel: threading.Event, **fields: object) -> None:
        with self.lock:
            if not cancel.is_set() and entry_id in self.jobs:
                job = self.jobs[entry_id]

                for key, value in fields.items():
                    setattr(job, key, value)

    def batch_progress(self) -> BatchProgress:
        # Without sizes in the catalog, only finished mods can be counted.
        with self.lock:
            batch = self.batch
            running = sum(job.done + job.sent for job in self.jobs.values() if job.phase != "error")

            done = batch.passed + running
            fraction = done / batch.total if batch.total else batch.finished / max(1, batch.count)

            return BatchProgress(
                active=self.busy(),
                number=self.batch_number,
                count=batch.count,
                finished=batch.finished,
                saved=batch.saved,
                failed=batch.failed,
                cancelled=batch.cancelled,
                uploaded=batch.uploaded,
                upload_failed=batch.upload_failed,
                deleted=batch.deleted,
                fraction=min(1, fraction),
            )

    def _finish_batch_item(self, size: int, outcome: Outcome = "saved") -> None:
        with self.lock:
            setattr(self.batch, outcome, getattr(self.batch, outcome) + 1)
            self.batch.finished += 1
            self.batch.passed += size

    def clear_error(self, entry_id: str) -> None:
        with self.lock:
            owner = self._job_owner(entry_id=entry_id)
            job = self.jobs.get(owner)

            if job and job.phase == "error":
                del self.jobs[owner]
