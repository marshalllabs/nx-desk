import time
from typing import Callable

from .. import uploader
from ..schemas.download import TransferMark
from ..schemas.github import Transfer, UploadSnapshot
from ..utils.sizes import format_size
from .github_auth import GitHubAuth


class GitHubJob(GitHubAuth):
    def upload_snapshot(self) -> UploadSnapshot:
        with self.lock:
            job = self.upload_job

            # Copies, so the UI never sees a folder or a progress line change while it paints.
            fields = {
                **dict(job),
                "folders": [folder.model_copy() for folder in job.folders],
                "item_progress": dict(job.item_progress),
                "source": self.upload_source,
            }

            return UploadSnapshot(**fields, log=list(self.github_log), github_ready=self.github_ready)

    def _speed(self) -> float:
        with self.lock:
            transfer = self.upload_job.transfer

            return transfer.speed if transfer else 0

    # What the current transfer has moved, for the GitHub tab's bar. Speed is worked out from
    # samples at least half a second apart, so short bursts do not make it jump.
    def _meter(self, label: str, done: int, total: int) -> None:
        now = time.monotonic()

        with self.lock:
            mark = self.meter_mark
            shown = self.upload_job.transfer
            same = shown is not None and shown.label == label

            if mark is None or done < mark.done or not same:
                self.meter_mark = TransferMark(time=now, done=done)
                speed = shown.speed if shown is not None and same else 0

            elif now - mark.time >= 0.5:
                speed = (done - mark.done) / (now - mark.time)
                self.meter_mark = TransferMark(time=now, done=done)

            else:
                return

            self.upload_job.transfer = Transfer(label=label, done=min(done, total), total=total, speed=speed)

    # A row's own share of the current transfer, for the Status columns.
    def _progress_text(self, verb: str, done: int, total: int) -> str:
        speed = self._speed()
        text = f"{verb} {min(100, 100 * done / max(1, total)):.0f}%"

        return f"{text} · {format_size(value=speed)}/s" if speed > 0 else text

    def _set_item(self, key: str, text: str = "") -> None:
        with self.lock:
            items = dict(self.upload_job.item_progress)

            if text:
                items[key] = text

            else:
                items.pop(key, None)

            self.upload_job.item_progress = items

    def _end_meter(self) -> None:
        with self.lock:
            self.meter_mark = None
            self.upload_job.transfer = None

    def uploading(self) -> bool:
        with self.lock:
            return self.upload_job.phase != "idle"

    # True while a GitHub job sends files or changes a release; quitting then leaves it half done.
    def changing_github(self) -> bool:
        with self.lock:
            return self.upload_job.phase in ("uploading", "changing")

    def _set_upload(self, **fields: object) -> None:
        with self.lock:
            for key, value in fields.items():
                setattr(self.upload_job, key, value)

    def _checked_repo(self, repo: str) -> str:
        if not uploader.releases.REPO_NAME.match(string=repo):
            raise ValueError("Enter the repository as owner/name")

        self._login()

        return repo

    def _upload_repo(self) -> str:
        return self._checked_repo(repo=self.upload_repo)

    # Authentication problems need the user to act, so they raise a popup instead of a quiet status line.
    def _run_upload_step(self, phase: str, step: Callable[[], str], quiet: bool = False) -> None:
        self._set_upload(phase=phase, message="Working with GitHub…", failed=False)

        try:
            message = step()
            self._set_upload(phase="idle", message=message)

            if message:
                self._log_github(text=message)

        except (uploader.command.GitHubError, ValueError, OSError) as error:
            with self.lock:
                alerts = self.upload_job.alerts + (0 if quiet else 1)

            text = str(error) or type(error).__name__
            self._set_upload(phase="idle", message=text, failed=True, alerts=alerts)
            self._log_github(text=text, level="error")

    @staticmethod
    def _listed(name: str) -> bool:
        return not name.startswith(uploader.archive.TEMP_PREFIX) and name != uploader.state.STATE_ASSET

    def _wait_for_github(self) -> None:
        if self.github_lock.locked():
            self._set_upload(message="Waiting for an automatic upload to finish…", failed=False)
