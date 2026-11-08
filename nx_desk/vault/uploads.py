import collections
import functools
import shutil
import tempfile
import time
import zipfile
from collections.abc import Collection
from pathlib import Path

from .. import uploader
from ..names import format_size
from ..schemas.common import Progress, Report
from ..schemas.github import Folder, FolderRef
from ..utils.callbacks import quiet
from ..zips import Cancelled
from .releases import Releases


class Uploads(Releases):
    def _upload_one(
        self,
        folder: FolderRef,
        repo: str,
        tag: str,
        stem: str,
        work: Path,
        report: Report | None = None,
        moved: Progress = quiet,
        zipped: Progress = quiet,
    ) -> None:
        place = Path(tempfile.mkdtemp(dir=work))

        if report is None:
            report = functools.partial(self._log_folder, folder.name)

        try:
            target = place / f"{uploader.archive.asset_base(folder=folder.path)}.zip"
            report(f"zipping the folder ({format_size(value=folder.size)})")
            uploader.archive.build_zip(folder=folder.path, target=target, moved=zipped)
            report(f"built {target.name} ({format_size(value=target.stat().st_size)})")
            parts = uploader.archive.split_file(path=target, part_size=uploader.archive.PART_SIZE, moved=zipped)

            if len(parts) > 1:
                report(f"split into {len(parts)} parts of up to {format_size(value=uploader.archive.PART_SIZE)}")

            assets = uploader.releases.remote_assets(repo=repo, tag=tag)
            uploader.parts.upload_parts(
                repo=repo,
                tag=tag,
                stem=stem,
                parts=parts,
                assets=assets,
                report=report,
                label=folder.name,
                moved=moved,
            )
        finally:
            shutil.rmtree(path=place, ignore_errors=True)

    def _chosen_stems(self, names: Collection[str]) -> dict[str, Folder]:
        with self.lock:
            chosen = [folder for folder in self.upload_job.folders if folder.name in names]

        stems: dict[str, Folder] = {}

        for folder in chosen:
            stem = uploader.archive.asset_stem(name=folder.name)

            if stem in stems:
                raise ValueError(f"Two folders get the same GitHub name: {stems[stem].name} and {folder.name}")

            stems[stem] = folder

        return stems

    def upload_folders(self, names: Collection[str]) -> None:
        self._wait_for_github()

        with self.github_lock:
            self._upload_folders(names=names)

    def _upload_folders(self, names: Collection[str]) -> None:
        tag = self.upload_tag
        self.upload_cancel.clear()

        try:
            repo = self._upload_repo()

            if not tag:
                raise ValueError("Choose a release")

            stems = self._chosen_stems(names=names)

            uploader.releases.delete_leftovers(repo=repo, tag=tag)
        except (uploader.command.GhError, ValueError, OSError) as error:
            with self.lock:
                alerts = self.upload_job.alerts + 1

            self._set_upload(message=str(error) or type(error).__name__, failed=True, alerts=alerts)

            return

        self._set_upload(
            phase="uploading",
            done=0,
            total=len(stems),
            message="",
            failed=False,
            fresh_assets=[],
            fresh_folders=[],
        )
        self._log_github(text=f"Uploading {len(stems)} mods to release {tag} of {repo}")
        self.parts.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="upload-", dir=self.parts))
        results: collections.Counter[str] = collections.Counter()
        failed: list[str] = []
        total = sum(folder.size for folder in stems.values())
        before = 0

        for folder in stems.values():
            self._mark_folder(name=folder.name, progress="Queued")

        try:
            # Smallest first, so one huge folder does not hold up all the others.
            order = sorted(stems.items(), key=lambda item: (item[1].size, item[0]))

            for index, (stem, folder) in enumerate(order):
                if self.upload_cancel.is_set():
                    break

                self._set_upload(done=index, message=f"Uploading {index + 1}/{len(stems)}: {folder.name}")
                self._mark_folder(name=folder.name, status="working", message="")
                started = time.monotonic()
                label = f"Uploading {index + 1}/{len(stems)}"

                def moved(
                    sent: int,
                    label: str = label,
                    before: int = before,
                    name: str = folder.name,
                    size: int = folder.size,
                ) -> None:
                    self._meter(label=label, done=before + sent, total=total)
                    self._mark_folder(name=name, progress=self._progress_text(verb="Uploading", done=sent, total=size))

                # Zipping has its own speed and size, so it shows on its own, not in the run's total.
                stage = f"Zipping {index + 1}/{len(stems)}"

                def zipped(
                    done: int,
                    stage: str = stage,
                    name: str = folder.name,
                    size: int = folder.size,
                ) -> None:
                    self._meter(label=stage, done=done, total=size)
                    self._mark_folder(name=name, progress=self._progress_text(verb="Zipping", done=done, total=size))

                try:
                    with uploader.command.stoppable(cancel=self.upload_cancel):
                        self._upload_one(
                            folder=folder,
                            repo=repo,
                            tag=tag,
                            stem=stem,
                            work=work,
                            moved=moved,
                            zipped=zipped,
                        )

                    outcome = "done"
                    self._mark_folder(name=folder.name, status=outcome)
                    self._log_folder(
                        folder_name=folder.name,
                        text=f"uploaded in {time.monotonic() - started:.0f}s",
                        level="ok",
                    )
                    self._refresh_assets(repo=repo, tag=tag, new_stem=stem)
                    # Recorded at once, so stopping midway leaves nothing uploaded unrecorded.
                    self._mark_folder(name=folder.name, progress="Updating state.json")

                    try:
                        self._record_in_state(repo=repo, tag=tag, folder_names=[folder.name])
                        recorded = True
                    except (uploader.command.GhError, OSError) as error:
                        recorded = False
                        text = f"could not update {uploader.state.STATE_ASSET}, the next upload will: {error}"
                        self._log_folder(folder_name=folder.name, text=text, level="error")

                    # Like automatic uploads, the local copy goes only after state.json knows it.
                    with self.lock:
                        delete = recorded and self.upload_delete and not self.upload_cancel.is_set()

                    if delete:
                        self._mark_folder(name=folder.name, progress="Deleting local copy")

                        if self._delete_local(folder=folder):
                            results["deleted"] += 1
                except (uploader.command.GhError, OSError, zipfile.BadZipFile) as error:
                    outcome = "error"
                    text = str(error) or type(error).__name__
                    self._mark_folder(name=folder.name, status="error", message=text)
                    failed.append(folder.name)
                    self._log_folder(folder_name=folder.name, text=f"failed: {text}", level="error")
                except Cancelled:
                    self._mark_folder(name=folder.name, status="", message="")
                    self._log_folder(
                        folder_name=folder.name,
                        text="cancelled, the release keeps its old copy",
                        level="warn",
                    )
                    break

                results[outcome] += 1
                before += folder.size
                self._mark_folder(name=folder.name, progress="")
        finally:
            shutil.rmtree(path=work, ignore_errors=True)
            self._end_meter()

            for folder in stems.values():
                self._mark_folder(name=folder.name, progress="")

        message = f"Uploaded {results['done']}, {results['error']} failed."

        if results["deleted"]:
            copies = "local copy" if results["deleted"] == 1 else "local copies"
            message += f" Deleted {results['deleted']} {copies}."

        message = "Cancelled. " + message if self.upload_cancel.is_set() else message
        self._log_github(
            text=message,
            level="error" if results["error"] else "warn" if self.upload_cancel.is_set() else "ok",
        )

        try:
            self._refresh_assets(repo=repo, tag=tag)
        except uploader.command.GhError as error:
            message += f" Could not reload the release: {error}"

        if results["deleted"]:
            try:
                self._scan_source()
            except (OSError, ValueError) as error:
                message += f" Could not scan the source folder: {error}"

        with self.lock:
            runs = self.upload_job.runs + 1

        self._set_upload(
            phase="idle",
            done=len(stems),
            message=message,
            failed=bool(results["error"]),
            runs=runs,
            retry_kind="upload",
            retry_names=failed,
            retry_tag=tag,
        )
