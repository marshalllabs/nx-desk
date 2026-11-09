import collections
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Collection, Counter, Dict, List, Optional

from .. import uploader
from ..names import safe_name
from ..schemas.common import Progress
from ..schemas.github import Asset
from ..utils.callbacks import quiet
from ..zips import Cancelled
from .source import UploadSource


class AssetDownloads(UploadSource):
    def _download_groups(self, names: Optional[Collection[str]], assets: Dict[str, Asset]) -> List[List[str]]:
        groups: Dict[str, List[str]] = {}

        for name in assets:
            if self._listed(name=name) and (names is None or name in names):
                groups.setdefault(uploader.parts.group_key(name=name), []).append(name)

        return sorted(groups.values(), key=lambda group: (sum(assets[name].size for name in group), group))

    def _download_one(
        self,
        group: List[str],
        repo: str,
        tag: str,
        assets: Dict[str, Asset],
        root: Path,
        work: Path,
        owner: str,
        moved: Progress = quiet,
    ) -> str:
        place = Path(tempfile.mkdtemp(dir=work))

        def report(text: str) -> None:
            self._log_folder(folder_name=owner, text=text)

        try:
            archive = uploader.parts.download_group(
                repo=repo,
                tag=tag,
                names=sorted(group),
                assets=assets,
                place=place,
                report=report,
                moved=moved,
            )
            self._set_item(key=uploader.parts.group_key(name=group[0]), text="Unpacking")
            report(text=f"extracting into {root}")

            return uploader.archive.extract_folder(archive=archive, root=root, place=place)

        finally:
            shutil.rmtree(path=place, ignore_errors=True)

    def download_assets(self, names: Optional[Collection[str]] = None) -> None:
        self._wait_for_github()

        with self.github_lock:
            self._download_assets(names=names)

    # A release's files stay together: in its catalog folder when there is one, else in [release].
    @staticmethod
    def _download_target(root: Path, tag: str) -> Path:
        name = safe_name(name=tag)

        if root.name in (name, f"[{name}]"):
            return root

        return root / name if (root / name).is_dir() else root / f"[{name}]"

    def _download_assets(self, names: Optional[Collection[str]]) -> None:
        tag = self.upload_tag
        self.upload_cancel.clear()

        try:
            repo = self._upload_repo()
            root = Path(self.upload_source).expanduser().resolve()

            if not tag or not self.upload_source or not root.is_dir():
                raise ValueError("Choose a release and a source folder")

            assets = uploader.releases.remote_assets(repo=repo, tag=tag)

        except (uploader.command.GhError, ValueError, OSError) as error:
            with self.lock:
                alerts = self.upload_job.alerts + 1

            self._set_upload(message=str(error) or type(error).__name__, failed=True, alerts=alerts)

            return

        groups = self._download_groups(names=names, assets=assets)
        self._set_upload(
            phase="uploading",
            done=0,
            total=len(groups),
            message="",
            failed=False,
            fresh_assets=[],
            fresh_folders=[],
        )
        root = self._download_target(root=root, tag=tag)

        with self.lock:
            owners = {folder.asset: folder.name for folder in self.upload_job.folders}

        for name, asset in assets.items():
            label = asset.label

            if label and uploader.parts.group_key(name=name) not in owners:
                owners[uploader.parts.group_key(name=name)] = label

        self._log_github(text=f"Downloading {len(groups)} items of release {tag} into {root}")
        self.parts.mkdir(exist_ok=True)
        root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="download-", dir=self.parts))
        results: Counter[str] = collections.Counter()
        failures: List[str] = []
        failed: List[str] = []
        fresh: List[str] = []
        total = sum(assets[name].size or 0 for group in groups for name in group)
        before = 0
        self._set_upload(item_progress={uploader.parts.group_key(name=group[0]): "Queued" for group in groups})

        try:
            for index, group in enumerate(iterable=groups):
                if self.upload_cancel.is_set():
                    break

                key = uploader.parts.group_key(name=group[0])
                owner = owners.get(key, key)
                self._set_upload(done=index, message=f"Downloading {index + 1}/{len(groups)}: {key}")
                started = time.monotonic()
                label = f"Downloading {index + 1}/{len(groups)}"

                def moved(
                    got: int,
                    label: str = label,
                    before: int = before,
                    key: str = key,
                    group: List[str] = group,
                ) -> None:
                    self._meter(label=label, done=before + got, total=total)
                    size = sum(assets[name].size or 0 for name in group)
                    self._set_item(key=key, text=self._progress_text(verb="Downloading", done=got, total=size))

                try:
                    with uploader.command.stoppable(cancel=self.upload_cancel):
                        saved = self._download_one(
                            group=group,
                            repo=repo,
                            tag=tag,
                            assets=assets,
                            root=root,
                            work=work,
                            owner=owner,
                            moved=moved,
                        )

                    fresh.append(saved)
                    results["done"] += 1
                    self._log_folder(
                        folder_name=owner,
                        text=f"saved as {saved} in {time.monotonic() - started:.0f}s",
                        level="ok",
                    )
                    # Scanned after each one, so the source panel fills in as files arrive.
                    self._set_upload(fresh_folders=list(fresh))
                    self._scan_source()

                except (uploader.command.GhError, OSError, zipfile.BadZipFile, shutil.Error) as error:
                    failures.append(f"{key}: {error}")
                    failed += group
                    self._log_folder(folder_name=owner, text=f"failed: {error}", level="error")

                except Cancelled:
                    self._log_folder(folder_name=owner, text="cancelled, nothing was saved", level="warn")
                    break

                before += sum(assets[name].size or 0 for name in group)
                self._set_item(key=key)

        finally:
            shutil.rmtree(path=work, ignore_errors=True)
            self._end_meter()
            self._set_upload(item_progress={})

        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()

        self._set_upload(fresh_folders=fresh)
        self._scan_source()
        message = f"Downloaded {results['done']}, {len(failures)} failed."

        if failures:
            message += " " + "; ".join(failures)

        message = "Cancelled. " + message if self.upload_cancel.is_set() else message
        self._log_github(text=message, level="error" if failures else "warn" if self.upload_cancel.is_set() else "ok")

        with self.lock:
            runs = self.upload_job.runs + 1

        self._set_upload(
            phase="idle",
            done=len(groups),
            message=message,
            failed=bool(failures),
            runs=runs,
            retry_kind="download",
            retry_names=failed,
            retry_tag=tag,
        )
