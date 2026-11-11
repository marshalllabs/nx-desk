import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .. import uploader
from ..config import STATE_FILE
from ..schemas.catalog import Catalog, Mod
from ..schemas.github import Asset
from ..schemas.release_state import ReleaseDocument, ReleaseRecord
from ..schemas.state import DOWNLOAD_RECORDS, RELEASE_STATE, ReleaseState
from ..utils.dates import parse_time
from ..utils.release_state import assets_present, build_record, content_matches, find_record, refresh_metadata
from .github_auth import GitHubAuth

# Changes the mods of state.json, given the release files as they are now.
StateChange = Callable[[Dict[str, ReleaseRecord], Dict[str, Asset]], None]


class ReleaseStates(GitHubAuth):
    def linked_catalog(self, tag: str) -> Optional[Catalog]:
        return next((catalog for catalog in self.catalogs if catalog.folder == tag), None)

    # Only used when local copies are deleted after upload; otherwise the disk alone decides.
    def _remote_record(self, entry: Mod) -> Optional[ReleaseRecord]:
        cache = self.release_state

        if not self.auto_delete or not self.catalog or cache.repo != self.auto_repo:
            return None

        if cache.tag != self.catalog.folder:
            return None

        mods = cache.mods or {}

        # Entries of one file share its upload, which state.json may hold under either.
        found = next(
            (
                mods[other]
                for other in self._ids_of(entry=entry)
                if other in mods and (cache.assets is None or assets_present(record=mods[other], names=cache.assets))
            ),
            None,
        )
        found = found or find_record(records=mods, entry_id=entry.id, sha256=entry.sha256)

        return found if found and (cache.assets is None or assets_present(record=found, names=cache.assets)) else None

    def _source_failures(self, entry: Mod) -> int:
        cache = self.release_state

        if not self.catalog or cache.repo != self.auto_repo or cache.tag != self.catalog.folder:
            return 0

        record = cache.mods.get(entry.id)
        failure = record.failure if record else None

        if failure and failure.sha256 == entry.sha256 and failure.size == entry.size:
            return failure.count

        return 0

    def _read_release_state(self, repo: str, tag: str, assets: Dict[str, Asset]) -> ReleaseState:
        path = self._release_cache(folder=tag)
        cache = self._load_model(path=path, schema=RELEASE_STATE, default=ReleaseState())
        asset = assets.get(uploader.state.STATE_ASSET)
        digest = (asset.digest or "") if asset else ""
        mods: Dict[str, ReleaseRecord]

        if not asset:
            mods = {}

        elif digest and cache.repo == repo and cache.digest == digest:
            mods = cache.mods

        else:
            self.parts.mkdir(exist_ok=True)
            place = Path(tempfile.mkdtemp(prefix="state-", dir=self.parts))

            try:
                mods = uploader.state.read_state(repo=repo, tag=tag, asset=asset, place=place)

            finally:
                shutil.rmtree(path=place, ignore_errors=True)

        data: ReleaseState = ReleaseState(repo=repo, tag=tag, digest=digest, mods=mods, assets=list(assets))
        self._keep_release_state(tag=tag, data=data)

        return data

    # The cache belongs to the Catalog tab's repository; the GitHub tab may be working on another.
    def _keep_release_state(self, tag: str, data: ReleaseState) -> None:
        if data.repo != self.auto_repo:
            return

        self._write_json(path=self._release_cache(folder=tag), value=data)

        with self.lock:
            if self.catalog and self.catalog.folder == tag:
                self.release_state = data

    def _forget_release_state(self, repo: str, tag: str) -> None:
        if repo != self.auto_repo:
            return

        self._release_cache(folder=tag).unlink(missing_ok=True)

        with self.lock:
            if self.catalog and self.catalog.folder == tag:
                self.release_state = ReleaseState()

    # Reads state.json of the active catalog's release when it changed. A GitHub job holds the
    # lock while it rewrites the file, and keeps the cache current itself, so this then waits.
    def refresh_release_state(self) -> Optional[ReleaseState]:
        with self.lock:
            tag = self.catalog.folder if self.catalog else ""
            repo = self.auto_repo
            wanted = tag and uploader.releases.REPO_NAME.match(string=repo)

        if not wanted or not self.github_lock.acquire(blocking=False):
            return None

        try:
            self._bind_github()

            try:
                assets = uploader.releases.remote_assets(repo=repo, tag=tag)

            except uploader.command.GitHubError:
                if tag in uploader.releases.list_releases(repo=repo):
                    raise

                assets = {}

            data = self._read_release_state(repo=repo, tag=tag, assets=assets)
            self._note_release_error(text="")

            return data

        except (uploader.command.GitHubError, OSError) as error:
            self._note_release_error(text=str(error) or type(error).__name__)

            return None

        finally:
            self.github_lock.release()

    def _note_release_error(self, text: str) -> None:
        with self.lock:
            changed = text != self.release_error
            self.release_error = text

        if changed and text:
            self._log_download(text=f"Could not read {uploader.state.STATE_ASSET} from GitHub: {text}", level="warn")

    def _state_record(
        self,
        sha256: Optional[str],
        version: Optional[str],
        folder: str,
        files: List[str],
        game_version: str = "",
    ) -> ReleaseRecord:
        return build_record(
            sha256=sha256 or "",
            version=version or "",
            game_version=game_version,
            folder=folder,
            files=files,
        )

    # Mods on the release that state.json lacks, such as after an upload cut off midway, found
    # through the catalog's download records. A file name does not carry the mod version, so a
    # record counts only when the file went up after that download: an older upload under the
    # same name may hold an older release of the mod, and a missing entry beats a wrong one.
    def _missing_from_state(
        self,
        tag: str,
        assets: Dict[str, Asset],
        mods: Dict[str, ReleaseRecord],
    ) -> Dict[str, ReleaseRecord]:
        records = self._load_model(
            path=self._catalog_file(folder=tag, name=STATE_FILE),
            schema=DOWNLOAD_RECORDS,
            default={},
        )
        found = {}

        for entry_id, record in records.items():
            folder = record.file.split(sep="/")[0]

            if entry_id in mods or not folder:
                continue

            files = uploader.parts.owned_assets(stem=uploader.archive.asset_stem(name=folder), assets=assets)
            downloaded = parse_time(value=record.downloaded_at)
            uploaded = [stamp for asset in files.values() if (stamp := parse_time(value=asset.updated_at))]

            if files and downloaded and len(uploaded) == len(files) and min(uploaded) >= downloaded:
                found[entry_id] = self._state_record(
                    sha256=record.sha256,
                    version=record.version,
                    folder=folder,
                    files=list(files),
                    game_version=record.game_version,
                )

        return found

    # Callers hold github_lock. state.json is read again first, so nothing written since is lost,
    # and entries already there are never replaced by what this machine remembers.
    def _write_release_state(self, repo: str, tag: str, change: StateChange) -> None:
        assets = uploader.releases.remote_assets(repo=repo, tag=tag)
        mods = dict(self._read_release_state(repo=repo, tag=tag, assets=assets).mods or {})
        found = self._missing_from_state(tag=tag, assets=assets, mods=mods)

        if found:
            mods.update(found)
            names = ", ".join(sorted(record.folder for record in found.values()))
            self._log_github(text=f"added to {uploader.state.STATE_ASSET} from download records: {names}")

        change(mods, assets)
        catalog = self.linked_catalog(tag=tag)

        with self.lock:
            entries = list(self.items) if catalog and self.catalog and self.catalog.folder == tag else []

        for entry in entries:
            direct = mods.get(entry.id)
            record = find_record(records=mods, entry_id=entry.id, sha256=entry.sha256)

            if (
                record
                and assets_present(record=record, names=list(assets))
                and content_matches(
                    record=record,
                    sha256=entry.sha256,
                    version=entry.version,
                    game_version=entry.game_version,
                )
            ):
                mods[entry.id] = refresh_metadata(
                    record=record,
                    sha256=entry.sha256,
                    version=entry.version,
                    game_version=entry.game_version,
                    names=list(assets),
                ).model_copy(update={"failure": direct.failure if direct else None})

        body = ReleaseDocument(catalog=catalog.url if catalog else "", mods=mods)
        self.parts.mkdir(exist_ok=True)
        place = Path(tempfile.mkdtemp(prefix="state-", dir=self.parts))

        try:
            path = place / uploader.state.STATE_ASSET
            path.write_text(
                data=body.model_dump_json(indent=1),
                encoding="utf-8",
            )
            digest = uploader.state.replace_asset(repo=repo, tag=tag, path=path)

        finally:
            shutil.rmtree(path=place, ignore_errors=True)

        self._keep_release_state(tag=tag, data=ReleaseState(repo=repo, tag=tag, digest=digest, mods=mods))
