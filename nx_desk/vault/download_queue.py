import threading
import time
from pathlib import Path
from typing import Iterable

from .. import net, zips
from ..names import clean_game_name, download_path
from ..schemas.catalog import Mod
from ..schemas.download import DownloadTask, Fetched, Job, RepackTask
from ..utils.sizes import format_size
from ..zips import Cancelled
from .auto_upload import AutoUploads
from .fetch import Fetching


class DownloadQueue(AutoUploads, Fetching):
    def enqueue(self, ids: Iterable[str]) -> None:
        with self.lock:
            if not self.busy():
                self.batch = self.new_batch()
                self.batch_number += 1

            known = {entry.id: entry for entry in self.items}
            # Put in by size: an idle worker takes the first mod the moment it is put, before the queue
            # can order the rest, so a big mod listed first used to start ahead of smaller ones.
            chosen = sorted((known[entry_id] for entry_id in ids if entry_id in known), key=lambda entry: entry.size)

            for entry in chosen:
                entry_id = entry.id

                # Entries of one file share a download, so one already running covers the rest.
                if not any(other in self.jobs for other in self._ids_of(entry=entry)):
                    self.batch.count += 1
                    # An upload moves the same bytes again, so it counts as much as the download.
                    weight = entry.size * (2 if self._will_auto_upload() else 1)
                    self.batch.total += weight
                    self.jobs[entry_id] = Job(
                        phase="queued",
                        done=0,
                        total=entry.size,
                        speed=0,
                        game=clean_game_name(name=entry.name),
                        weight=weight,
                    )
                    # The event also tells this run apart from a later one of the same mod.
                    cancel = self.cancels[entry_id] = threading.Event()
                    self.queue.put(
                        item=DownloadTask(
                            priority=entry.size,
                            order=next(self.queue_order),
                            entry=entry,
                            cancel=cancel,
                        ),
                    )
                    size = f" ({format_size(value=entry.size)})" if entry.size else ""
                    self._log_game(entry=entry, text=f"queued{size}")

    # Called with the lock held. The job ends at once: an open connection is shut so a read that
    # waits on a slow server wakes up, and the worker leaves quietly when it sees the event.
    def _stop(self, entry_id: str) -> bool:
        cancel = self.cancels.get(entry_id)
        job = self.jobs.get(entry_id)

        if not cancel or not job or job.phase == "error":
            return False

        del self.cancels[entry_id]
        cancel.set()
        response = self.responses.pop(entry_id, None)

        if response is not None:
            net.abort(response=response)

        del self.jobs[entry_id]
        self._finish_batch_item(size=(job.weight or job.total), outcome="cancelled")
        where = f" at {format_size(value=job.done)}" if job.done else ""
        self._log_download(text=f"stopped while {job.phase}{where}", level="warn", game=job.game)

        return True

    def cancel(self, entry_id: str) -> None:
        with self.lock:
            self._stop(entry_id=self._job_owner(entry_id=entry_id))

    def cancel_all(self) -> None:
        with self.lock:
            stopped = sum(self._stop(entry_id=entry_id) for entry_id in list(self.cancels))

            if stopped:
                self._log_download(text=f"Stopped all {stopped} downloads", level="warn")

    def worker(self) -> None:
        while True:
            task = self.queue.get()
            entry, cancel = task.entry, task.cancel

            with self.lock:
                current = self.cancels.get(entry.id) is cancel

            if not current:
                continue

            # A stopped run of the same mod may still be leaving; it shares the partial file.
            with self.part_locks[entry.id]:
                self._run_download(entry=entry, cancel=cancel)

    def repack_worker(self) -> None:
        while True:
            self._repack_next()

    def _repack_next(self) -> None:
        task = self.repack_queue.get()
        entry, fetched, target, cancel, started = task.entry, task.fetched, task.target, task.cancel, task.started

        if cancel.is_set():
            return

        with self.part_locks[entry.id], self.target_locks[target]:
            self._run_repack(entry=entry, fetched=fetched, target=target, cancel=cancel, started=started)

    def _fail_job(self, entry: Mod, cancel: threading.Event, error: Exception) -> None:
        with self.lock:
            if not cancel.is_set() and entry.id in self.jobs:
                self._log_game(entry=entry, text=f"error: {error}", level="error")
                self.jobs[entry.id].phase = "error"
                self.jobs[entry.id].message = str(error)
                self.jobs[entry.id].speed = 0
                self._finish_batch_item(size=self.jobs[entry.id].weight, outcome="failed")

    def _forget_cancel(self, entry_id: str, cancel: threading.Event) -> None:
        with self.lock:
            if self.cancels.get(entry_id) is cancel:
                del self.cancels[entry_id]

    # Repacking has its own queue, so a slow one leaves the download slot free for the next mod.
    def _run_download(self, entry: Mod, cancel: threading.Event) -> None:
        entry_id = entry.id
        name = entry.save_name or entry.name
        target = self.root / download_path(name=name, version=entry.game_version, mod=self.mod_name)
        started = time.monotonic()

        try:
            if cancel.is_set():
                raise Cancelled

            self._update_job(entry_id=entry_id, cancel=cancel, phase="downloading")
            self._log_game(entry=entry, text=f"starting, will save as {target.name}")
            fetched = self._download(entry=entry, cancel=cancel)
            self._update_job(entry_id=entry_id, cancel=cancel, phase="waiting_repack", speed=0)
            self.repack_queue.put(
                item=RepackTask(
                    priority=entry.size,
                    order=next(self.queue_order),
                    entry=entry,
                    fetched=fetched,
                    target=target,
                    cancel=cancel,
                    started=started,
                ),
            )

            return

        except Cancelled:
            pass

        except Exception as error:
            self._fail_job(entry=entry, cancel=cancel, error=error)

        self._forget_cancel(entry_id=entry_id, cancel=cancel)

    def _run_repack(
        self,
        entry: Mod,
        fetched: Fetched,
        target: Path,
        cancel: threading.Event,
        started: float,
    ) -> None:
        entry_id = entry.id
        source = fetched.wire

        try:
            if cancel.is_set():
                raise Cancelled

            self._update_job(entry_id=entry_id, cancel=cancel, phase="repacking", speed=0)

            with self.lock:
                level = self.compression

            self._log_game(
                entry=entry,
                text=f"repacking {format_size(value=source.stat().st_size)} at compression level {level}",
            )
            zips.repack(source=source, target=target, title_id=entry.title_id, cancel=cancel, level=level)
            fetched.wire.unlink(missing_ok=True)
            replaced = self._commit(entry=entry, target=target)

            if replaced:
                self._log_game(entry=entry, text=f"removed the old copy {replaced.name}")

            spent = time.monotonic() - started
            size = format_size(value=target.stat().st_size)
            self._log_game(entry=entry, text=f"saved {target} ({size}) in {spent:.0f}s", level="ok")
            self._source_changed(path=target.parent)

            with self.lock:
                current = self.cancels.get(entry_id) is cancel
                upload = current and self._will_auto_upload()

                if current and not upload:
                    self._finish_batch_item(size=self.jobs.pop(entry_id).weight)

            if upload:
                self._update_job(entry_id=entry_id, cancel=cancel, phase="waiting_upload")
                self._queue_auto_upload(entry=entry, folder=target.parent, cancel=cancel, replaced=replaced)

                return

        except Cancelled:
            pass

        except Exception as error:
            self._fail_job(entry=entry, cancel=cancel, error=error)

        self._forget_cancel(entry_id=entry_id, cancel=cancel)
