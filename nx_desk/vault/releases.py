from collections.abc import Collection
from pathlib import Path

from .. import uploader
from ..config import STATE_FILE
from ..schemas.github import Asset
from ..schemas.state import DOWNLOAD_RECORDS, ReleaseRecord
from .release_state import ReleaseStates
from .source import UploadSource


class Releases(UploadSource, ReleaseStates):
    def _refresh_assets(self, repo: str, tag: str, new_stem: str | None = None) -> list[Asset]:
        assets = uploader.releases.remote_assets(repo=repo, tag=tag)
        rows = [asset for name, asset in assets.items() if self._listed(name=name)]
        added = list(uploader.parts.owned_assets(stem=new_stem, assets=assets)) if new_stem else []

        with self.lock:
            job = self.upload_job
            job.assets = rows
            job.asset_list = job.asset_list + 1
            job.fresh_assets = job.fresh_assets + added

        return rows

    def load_assets(self) -> None:
        def step() -> str:
            repo = self._upload_repo()

            if not self.upload_tag:
                raise ValueError("Choose a release")

            self._refresh_assets(repo=repo, tag=self.upload_tag)

            return self._follow_release(tag=self.upload_tag)

        self._run_upload_step(phase="loading", step=step)

    # Mods whose files were deleted by hand leave state.json too.
    def _forget_in_state(self, repo: str, tag: str, names: set[str]) -> None:
        if not self.linked_catalog(tag=tag) or uploader.state.STATE_ASSET not in uploader.releases.remote_assets(
            repo=repo,
            tag=tag,
        ):
            return

        gone = []

        def change(mods: dict[str, ReleaseRecord], _assets: dict[str, Asset]) -> None:
            for key in [key for key, record in mods.items() if names & set(record.files)]:
                gone.append(mods.pop(key).folder or key)

        self._write_release_state(repo=repo, tag=tag, change=change)

        if gone:
            self._log_github(text=f"removed {len(gone)} from {uploader.state.STATE_ASSET}: {', '.join(sorted(gone))}")

    # Folders uploaded by hand join state.json when this app downloaded them, which gives the
    # SHA-256 of the original file; others cannot be told apart from an older release.
    def _record_in_state(self, repo: str, tag: str, folder_names: list[str]) -> None:
        catalog = self.linked_catalog(tag=tag)

        if not catalog or not folder_names:
            return

        records = self._load_model(
            path=self._catalog_file(folder=catalog.folder, name=STATE_FILE),
            schema=DOWNLOAD_RECORDS,
            default={},
        )
        by_folder = {record.file.split("/")[0]: (entry_id, record) for entry_id, record in records.items()}
        known = [name for name in folder_names if name in by_folder]

        for name in sorted(set(folder_names) - set(known)):
            self._log_folder(
                folder_name=name,
                text=f"not added to {uploader.state.STATE_ASSET}: no download record of it",
                level="warn",
            )

        if not known:
            return

        def change(mods: dict[str, ReleaseRecord], assets: dict[str, Asset]) -> None:
            for name in known:
                entry_id, record = by_folder[name]
                files = list(uploader.parts.owned_assets(stem=uploader.archive.asset_stem(name=name), assets=assets))
                mods[entry_id] = self._state_record(
                    sha256=record.sha256,
                    version=record.version,
                    folder=name,
                    files=files,
                )

        self._write_release_state(repo=repo, tag=tag, change=change)

        for name in known:
            self._log_folder(folder_name=name, text=f"recorded in {uploader.state.STATE_ASSET}")

    def release_source(self, tag: str) -> Path | None:
        folder = self._download_root() / tag if tag and "/" not in tag and tag not in (".", "..") else None

        return folder if folder and folder.is_dir() else None

    # A release named like a catalog folder uses that folder as its source; any other release
    # uses the whole destination of the Catalog tab. The source is scanned again either way.
    def _follow_release(self, tag: str) -> str:
        folder = self.release_source(tag=tag)

        if folder is None:
            root = self._download_root()
            folder = root if root.is_dir() else None

        if folder is None:
            return ""

        with self.lock:
            same = bool(self.upload_source) and Path(self.upload_source).expanduser().resolve() == folder

            if not same:
                self.upload_source = str(folder)
                self._save_registry()
                self.upload_job.source_list += 1

        self._scan_source()

        return "" if same else f"Source folder set to {folder}."

    def delete_release_assets(self, names: Collection[str]) -> None:
        def step() -> str:
            repo = self._upload_repo()

            with self.github_lock:
                assets = uploader.releases.remote_assets(repo=repo, tag=self.upload_tag)
                chosen = [assets[name] for name in names if name in assets]

                for asset in chosen:
                    self._set_item(key=uploader.parts.group_key(name=asset.name), text="Deleting")

                for asset in chosen:
                    uploader.releases.delete_asset(repo=repo, asset=asset)
                    self._log_github(
                        text=f"deleted {asset.name} from release {self.upload_tag}",
                        level="warn",
                        game=asset.name,
                    )

                    with self.lock:
                        job = self.upload_job
                        rows = [row for row in job.assets if row.name != asset.name]
                        job.assets = rows
                        job.asset_list = job.asset_list + 1

                        # A finished upload's mark would keep showing the folder as uploaded.
                        for folder in job.folders:
                            if folder.asset == uploader.parts.group_key(name=asset.name):
                                folder.status = ""
                                folder.message = ""

                self._set_upload(item_progress={})
                self._forget_in_state(repo=repo, tag=self.upload_tag, names={asset.name for asset in chosen})
                self._refresh_assets(repo=repo, tag=self.upload_tag)

            return f"Deleted {len(chosen)} files from release {self.upload_tag}."

        self._run_upload_step(phase="changing", step=step)

    # Runs when the app opens, so a missing login stays a quiet status line, not a popup.
    def prepare_uploads(self) -> None:
        def step() -> str:
            parts = []

            if self.upload_source and Path(self.upload_source).expanduser().is_dir():
                parts.append(self._scan_source())

            self._refresh_repos()

            if self.upload_repo:
                parts.append(self._open_repo(repo=self._upload_repo()))

            return " ".join(filter(None, parts))

        self._run_upload_step(phase="loading", step=step, quiet=True)

    def _refresh_repos(self) -> None:
        self._login()
        repos = uploader.releases.list_repos()

        with self.lock:
            job = self.upload_job
            job.repos = [repo.full_name for repo in repos]
            job.repo_details = repos
            job.repo_list = job.repo_list + 1

    # The repository picker's reload, which leaves the chosen repository and release as they are.
    def load_repos(self) -> None:
        def step() -> str:
            self._refresh_repos()

            with self.lock:
                count = len(self.upload_job.repos)

            return f"Loaded {count} {'repository' if count == 1 else 'repositories'}."

        self._run_upload_step(phase="loading", step=step)

    # The latest release comes first and the rest by name. With no release named, the first is chosen.
    def _refresh_releases(self, repo: str, select: str | None = None) -> list[str]:
        tags = uploader.releases.list_releases(repo=repo)
        latest = uploader.releases.latest_release(repo=repo)
        latest = latest if latest in tags else ""
        order = ([latest] if latest else []) + sorted((tag for tag in tags if tag != latest), key=str.casefold)
        tag = (order[0] if order else "") if select is None else select

        with self.lock:
            job = self.upload_job
            job.releases = order
            job.latest_release = latest
            job.release_list = job.release_list + 1
            job.select_tag = tag
            self.upload_tag = tag

        return order

    def _open_repo(self, repo: str) -> str:
        self._refresh_releases(repo=repo)
        tag = self.upload_tag

        if not tag:
            with self.lock:
                job = self.upload_job
                job.assets = []
                job.asset_list = job.asset_list + 1

            return "The repository has no releases yet."

        self._refresh_assets(repo=repo, tag=tag)

        return self._follow_release(tag=tag)

    def load_releases(self) -> None:
        self._run_upload_step(phase="loading", step=lambda: self._open_repo(repo=self._upload_repo()))

    def reload_github(self) -> None:
        def step() -> str:
            self._refresh_repos()

            return self._open_repo(repo=self._upload_repo()) if self.upload_repo else "Loaded the repo list."

        self._run_upload_step(phase="loading", step=step)

    def create_upload_release(self, tag: str) -> None:
        def step() -> str:
            name = tag.strip()

            if not name:
                raise ValueError("Enter a new release name")

            repo = self._upload_repo()
            uploader.releases.create_release(repo=repo, tag=name)
            self._refresh_releases(repo=repo, select=name)
            self._refresh_assets(repo=repo, tag=name)

            return f"Created release {name}."

        self._run_upload_step(phase="changing", step=step)

    def rename_release(self, new_tag: str) -> None:
        def step() -> str:
            name = new_tag.strip()

            if not name:
                raise ValueError("Enter a new release name")

            repo = self._upload_repo()
            old = self.upload_tag

            with self.github_lock:
                uploader.releases.rename_release(repo=repo, tag=old, new_tag=name)

            if self.linked_catalog(tag=old):
                self._forget_release_state(repo=repo, tag=old)
                self._log_github(text=f"release {old} is no longer linked to its catalog", level="warn")

            self._refresh_releases(repo=repo, select=name)
            self._refresh_assets(repo=repo, tag=name)

            return f"Renamed the release to {name}."

        self._run_upload_step(phase="changing", step=step)

    def delete_release(self) -> None:
        def step() -> str:
            repo = self._upload_repo()
            tag = self.upload_tag

            with self.github_lock:
                uploader.releases.delete_release(repo=repo, tag=tag)

            if self.linked_catalog(tag=tag):
                self._forget_release_state(repo=repo, tag=tag)
                self._log_github(
                    text=f"release {tag} was linked to a catalog; its {uploader.state.STATE_ASSET} is gone",
                    level="warn",
                )

            self._open_repo(repo=repo)

            return f"Deleted release {tag}."

        self._run_upload_step(phase="changing", step=step)
