import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional, Tuple

from .. import uploader
from ..names import clean_game_name
from ..schemas.catalog import Mod
from ..schemas.download import Outcome
from ..schemas.github import Asset, AutoMod, AutoUpload, FolderRef
from ..schemas.release_state import ReleaseRecord
from ..utils.files import tree_size
from ..zips import Cancelled
from .jobs import Jobs
from .uploads import Uploads


class AutoUploads(Jobs, Uploads):
    def auto_uploading(self) -> bool:
        with self.lock:
            return self.auto_pending > 0

    # A saved mod goes to the release named after its catalog folder, created when missing.
    # The job stays open through these steps, so its status and the batch report tell how it ended.
    def _queue_auto_upload(
        self,
        entry: Mod,
        folder: Path,
        cancel: threading.Event,
        replaced: Optional[Path] = None,
    ) -> None:
        old = replaced.parent.name if replaced and replaced.parent.name != folder.name else ""
        mod: AutoMod = AutoMod(
            id=entry.id,
            twins=entry.twins or [],
            sha256=entry.sha256,
            version=entry.version,
            game_version=entry.game_version,
            size=entry.size,
            game=clean_game_name(name=entry.name),
        )

        with self.lock:
            self.auto_pending += 1
            self.auto_queue.put(item=AutoUpload(mod=mod, folder=folder, tag=folder.parent.name, old=old, cancel=cancel))
            self._mark_folder(name=folder.name, progress="Waiting to upload")

            if self.auto_thread is None:
                self.auto_thread = threading.Thread(target=self.auto_upload_worker, daemon=True)
                self.auto_thread.start()

        self._log_game(entry=entry, text=f"waiting to upload to release {folder.parent.name}")

    def auto_upload_worker(self) -> None:
        while True:
            task = self.auto_queue.get()
            mod, folder, tag, old, cancel = task.mod, task.folder, task.tag, task.old, task.cancel
            outcomes: Tuple[Outcome, ...] = ("upload_failed",)

            try:
                outcomes = self._auto_upload_one(mod=mod, folder=folder, tag=tag, cancel=cancel, old=old)

            finally:
                self._mark_folder(name=folder.name, progress="")
                self._finish_auto_upload(mod=mod, cancel=cancel, outcomes=outcomes)

    def _finish_auto_upload(self, mod: AutoMod, cancel: threading.Event, outcomes: Tuple[Outcome, ...]) -> None:
        with self.lock:
            self.auto_pending -= 1

            # A stopped job was already counted when it was stopped.
            if self.cancels.get(mod.id) is cancel:
                del self.cancels[mod.id]
                job = self.jobs.pop(mod.id)
                self._finish_batch_item(size=job.weight)

                for outcome in outcomes:
                    setattr(self.batch, outcome, getattr(self.batch, outcome) + 1)

    # Upload, record it in state.json, drop the version it replaced, then delete the local copy
    # if asked. Each step runs only when the one before it worked, so nothing is lost on an error.
    # Stop works until the upload is done; after that the release is left consistent first.
    def _auto_upload_one(
        self,
        mod: AutoMod,
        folder: Path,
        tag: str,
        cancel: threading.Event,
        old: str = "",
    ) -> Tuple[Outcome, ...]:
        def report(text: str, level: str = "info") -> None:
            self._log_download(text=text, level=level, game=mod.game)
            self._log_folder(folder_name=folder.name, text=text, level=level)

        try:
            with self.github_lock:
                if cancel.is_set():
                    return ()

                self._update_job(entry_id=mod.id, cancel=cancel, phase="zipping")
                repo = self._checked_repo(repo=self.auto_repo)
                stem = uploader.archive.asset_stem(name=folder.name)

                with uploader.command.stoppable(cancel=cancel):
                    if tag not in uploader.releases.list_releases(repo=repo):
                        uploader.releases.create_release(repo=repo, tag=tag)
                        report(text=f"created release {tag} in {repo}")

                        if repo == self.upload_repo:
                            self._refresh_releases(repo=repo, select=self.upload_tag)

                    else:
                        leftovers = uploader.releases.delete_leftovers(repo=repo, tag=tag)

                        if leftovers:
                            report(text=f"removed files left by a stopped upload: {', '.join(leftovers)}")

                    report(text=f"uploading to release {tag} of {repo}")
                    unit: FolderRef = FolderRef(name=folder.name, path=folder, size=tree_size(path=folder))

                    def zipped(done: int) -> None:
                        self._meter(label=f"Zipping {mod.game}", done=done, total=unit.size)
                        self._update_job(entry_id=mod.id, cancel=cancel, zipped=min(done, unit.size))
                        self._mark_folder(
                            name=folder.name,
                            progress=self._progress_text(verb="Zipping", done=done, total=unit.size),
                        )

                    def moved(sent: int) -> None:
                        self._meter(label=f"Uploading {mod.game}", done=sent, total=unit.size)

                        sent = min(sent, unit.size)
                        self._update_job(
                            entry_id=mod.id,
                            cancel=cancel,
                            phase="uploading",
                            sent=sent,
                            speed=self._speed(),
                        )
                        self._mark_folder(
                            name=folder.name,
                            progress=self._progress_text(verb="Uploading", done=sent, total=unit.size),
                        )

                    self.parts.mkdir(exist_ok=True)
                    work = Path(tempfile.mkdtemp(prefix="upload-", dir=self.parts))

                    try:
                        self._upload_one(
                            folder=unit,
                            repo=repo,
                            tag=tag,
                            stem=stem,
                            work=work,
                            report=report,
                            moved=moved,
                            zipped=zipped,
                        )

                    finally:
                        shutil.rmtree(path=work, ignore_errors=True)
                        self._end_meter()

                report(text=f"uploaded to release {tag}", level="ok")

                def record(mods: Dict[str, ReleaseRecord], assets: Dict[str, Asset]) -> None:
                    files = list(uploader.parts.owned_assets(stem=stem, assets=assets))

                    # Entries of the same file share this upload.
                    for entry_id in (mod.id, *mod.twins):
                        mods[entry_id] = self._state_record(
                            sha256=mod.sha256,
                            version=mod.version,
                            folder=folder.name,
                            files=files,
                            game_version=mod.game_version,
                        )

                self._update_job(entry_id=mod.id, cancel=cancel, phase="recording", speed=0, sent=mod.size)
                self._mark_folder(name=folder.name, progress="Updating state.json")
                self._write_release_state(repo=repo, tag=tag, change=record)
                report(text=f"recorded in {uploader.state.STATE_ASSET}")

                if old:
                    stale = uploader.parts.owned_assets(
                        stem=uploader.archive.asset_stem(name=old),
                        assets=uploader.releases.remote_assets(repo=repo, tag=tag),
                    )

                    for asset in stale.values():
                        uploader.releases.delete_asset(repo=repo, asset=asset)
                        report(text=f"removed {asset.name}, the version this one replaced")

                with self.lock:
                    delete = self.auto_delete and not cancel.is_set()

                outcomes: Tuple[Outcome, ...] = ("uploaded",)
                deleted = None

                if delete:
                    self._update_job(entry_id=mod.id, cancel=cancel, phase="deleting")
                    self._mark_folder(name=folder.name, progress="Deleting local copy")

                    try:
                        shutil.rmtree(path=folder)
                        deleted = folder
                        outcomes = ("uploaded", "deleted")
                        report(text=f"deleted the local copy {folder.name}")

                    except OSError as error:
                        report(text=f"could not delete the local copy: {error}", level="error")

                self._after_auto_upload(repo=repo, tag=tag, deleted=deleted)

                return outcomes

        except Cancelled:
            report(text="upload stopped, the local copy is kept", level="warn")

            return ()

        # This thread serves every later upload, so one surprise must not end it.
        except Exception as error:
            report(text=f"upload to GitHub failed: {str(error) or type(error).__name__}", level="error")

            return ("upload_failed",)

    # The GitHub tab may show this release or the deleted folder, so it is brought up to date.
    def _after_auto_upload(self, repo: str, tag: str, deleted: Optional[Path]) -> None:
        if repo == self.upload_repo and tag == self.upload_tag:
            self._refresh_assets(repo=repo, tag=tag)

        if deleted:
            self._source_changed(path=deleted)
