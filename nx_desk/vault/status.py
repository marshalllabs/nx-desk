import os
from pathlib import Path

from ..names import display_version, folder_version, game_folder, safe_name, version_label
from ..schemas.catalog import Mod
from ..schemas.snapshot import ModRow, Snapshot
from ..schemas.state import DownloadRecord, ReleaseRecord
from .jobs import Jobs
from .release_state import ReleaseStates


class Statuses(Jobs, ReleaseStates):
    def local_path(self, record: DownloadRecord) -> Path | None:
        path = (self.root / record.file).resolve()

        return path if self.root in path.parents else None

    def game_folders(self, entry: Mod) -> list[Path]:
        # Older saves may use the catalog's name or keep symbols that names now lose.
        names = {entry.name, (entry.catalog_name or entry.name), (entry.save_name or entry.name)}
        folders = {game_folder(name=name, mod=self.mod_name) for name in names}
        folders |= {f"{safe_name(name=name)} - [{self.mod_name}]" for name in names}
        # The version is part of the folder name now, so any version of this game counts.
        starts = tuple(f"{game_folder(name=name, mod=self.mod_name)} - [" for name in names)

        try:
            folders |= {name for name in os.listdir(path=self.root) if name.startswith(starts) and name.endswith("]")}
        except OSError:
            pass

        return [self.root / folder for folder in folders]

    def saved_zips(self, entry: Mod) -> list[Path]:
        zips = []

        for folder in self.game_folders(entry=entry):
            try:
                zips += [path for path in folder.iterdir() if path.suffix.lower() == ".zip" and path.is_file()]
            except OSError:
                pass

        return zips

    def status_of(self, entry: Mod) -> str:
        return self._status(entry=entry)[0]

    # Local copies decide first. Without one, state.json on the release does when local copies are
    # deleted after upload. The second value says the answer came from the release.
    def _status(self, entry: Mod) -> tuple[str, ReleaseRecord | None]:
        zips = self.saved_zips(entry=entry)

        if not zips:
            remote = self._remote_record(entry=entry)

            if not remote:
                return "missing", None

            if entry.sha256 and remote.sha256:
                return ("ok" if remote.sha256 == entry.sha256 else "update"), remote

            return ("ok" if remote.version == entry.version else "update"), remote

        return self._local_status(entry=entry, zips=zips), None

    def _local_status(self, entry: Mod, zips: list[Path]) -> str:
        record = self._record_of(entry=entry)

        if not record:
            # Copied in by hand, so its hash is unknown: only the name can say which version it is.
            older = f"[{display_version(game_version=entry.game_version)}-"
            current = f" - [{version_label(version=entry.game_version)}].zip"

            return (
                "ok" if any(path.name.startswith(older) or path.name.endswith(current) for path in zips) else "update"
            )

        # The original file's SHA-256 is the surest way to spot a new release. When the
        # catalog does not carry one, fall back to comparing the version it reports.
        if entry.sha256 and record.sha256:
            return "ok" if record.sha256 == entry.sha256 else "update"

        return "ok" if record.version == entry.version else "update"

    # Records from before game versions were stored still name their folder after it.
    @staticmethod
    def _saved_game_version(record: DownloadRecord | ReleaseRecord) -> str:
        if game_version := record.game_version:
            return game_version

        file = record.file if isinstance(record, DownloadRecord) else ""
        folder = record.folder or Path(file).parent.name

        return folder_version(folder=folder)

    def snapshot(self) -> Snapshot:
        with self.lock:
            items: list[ModRow] = []

            for entry in self.items:
                status, remote = self._status(entry=entry)
                saved: DownloadRecord | ReleaseRecord = remote or self._record_of(entry=entry) or DownloadRecord()
                # Entries of one file share its download, so each row shows the running job.
                owner = next((other for other in self._ids_of(entry=entry) if other in self.jobs), entry.id)
                row = ModRow(
                    **dict(entry),
                    status=status,
                    remote=remote is not None,
                    local_version=saved.version,
                    local_game_version=self._saved_game_version(record=saved),
                    job=self.jobs.get(owner),
                )
                items.append(row)

            return Snapshot(
                items=items,
                checked_at=self.checked_at,
                checking=self.checking,
                error=self.check_error,
                dir=str(self.root),
                catalogs=list(self.catalogs),
                active=self.catalog.folder if self.catalog else None,
                app_update=self.app_update,
                app_update_job=self.app_update_job,
                log=list(self.download_log),
                batch=self.batch_progress(),
            )
