import collections
import http.client
import itertools
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, TypeVar

from pydantic import TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python

from .. import uploader
from ..catalog.parse import parse_catalog
from ..catalog.ports import parse_ports
from ..catalog.title_ids import game_names, parse_title_ids
from ..catalog.values import clean_mapping
from ..config import (
    ART_LOOKUPS_FILE,
    CACHE_DIR,
    CATALOG_FILE,
    CATALOGS_DIR,
    DOWNLOAD_DIR,
    LOGS_DIR,
    NO_CATALOG,
    PORTS_ART_FOLDER,
    PORTS_FILE,
    RELEASE_FILE,
    SETTINGS_FILE,
    STATE_FILE,
    TITLE_IDS_FILE,
    clean_compression,
)
from ..names import BINARY, safe_name, set_size_units, title_name
from ..schemas.artwork import ART_LOOKUPS, ArtLookup, StoredSecret
from ..schemas.catalog import Catalog, Mod
from ..schemas.common import LogEntry
from ..schemas.download import Batch, DownloadTask, Job, RepackTask
from ..schemas.github import AutoUpload, UploadJob
from ..schemas.notice import Notice
from ..schemas.port import Port
from ..schemas.registry import REGISTRY, Registry
from ..schemas.state import DOWNLOAD_RECORDS, RELEASE_STATE, DownloadRecord, ReleaseState
from ..schemas.title import TitleRow
from ..schemas.update import AppUpdate, UpdateJob
from .layout import migrate_layout

T = TypeVar("T")


# What makes two entries the same file: its SHA-256, else its links; empty when neither is known.
def file_key(entry: Mod) -> str:
    if entry.sha256:
        return f"sha256:{entry.sha256.lower()}"

    return "urls:" + " ".join(entry.urls) if entry.urls else ""


class VaultBase:
    def __init__(self, base: Path | str) -> None:
        self.base = Path(base).resolve()
        # A folder made by an older version is brought to this layout before anything is read from it.
        migrate_layout(base=self.base)
        self.catalogs_dir = self.base / CATALOGS_DIR
        self.catalogs_dir.mkdir(parents=True, exist_ok=True)
        # Caches the app can fetch again; the rest of the data folder is not.
        self.cache_dir = self.base / CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.base / SETTINGS_FILE
        self.parts = self.base / ".parts"
        self.logs_dir = self.base / LOGS_DIR
        self.lock = threading.RLock()
        self.jobs: dict[str, Job] = {}
        self.cancels: dict[str, threading.Event] = {}
        self.responses: dict[str, http.client.HTTPResponse] = {}
        # A server rate limit pauses every download worker until this monotonic time; a repeated
        # limit means the server has not reset yet, so the pause grows.
        self.rate_until: float = 0.0
        self.rate_strikes: int = 0
        self.part_locks: collections.defaultdict[str, threading.Lock] = collections.defaultdict(threading.Lock)
        # One repack at a time writes a given zip, whichever entries lead there.
        self.target_locks: collections.defaultdict[Path, threading.Lock] = collections.defaultdict(threading.Lock)
        # Smallest first, wherever a download was started from. The counter settles equal sizes.
        self.queue: queue.PriorityQueue[DownloadTask] = queue.PriorityQueue()
        self.queue_order = itertools.count()
        self.repack_queue: queue.PriorityQueue[RepackTask] = queue.PriorityQueue()
        self.download_log: list[LogEntry] = []
        self.github_log: list[LogEntry] = []
        self.batch = self.new_batch()
        self.batch_number = 0
        self.checked_at: float | None = None
        self.check_error: str | None = None
        self.checking = False
        self.app_update: AppUpdate | None = None
        self.app_update_job: UpdateJob | None = None
        self.upload_cancel = threading.Event()
        # One GitHub job at a time: manual uploads, downloads and deletes, and automatic uploads.
        self.github_lock = threading.Lock()
        self.auto_queue: queue.Queue[AutoUpload] = queue.Queue()
        self.auto_thread: threading.Thread | None = None
        self.auto_pending = 0
        self.upload_job = UploadJob()
        self.meter_mark: tuple[float, int] | None = None
        self.title_version = 0
        self.title_loading = False
        self.title_error = ""
        self.port_version = 0
        self.port_loading = False
        self.port_error = ""
        # None until gh has answered once.
        self.gh_ready: bool | None = None
        registry = self._load_model(path=self.registry_path, schema=REGISTRY, default=Registry())
        self.title_rows: list[TitleRow] = parse_title_ids(
            data=self._load_json(path=self.cache_dir / TITLE_IDS_FILE, default={}),
        )
        self.titles: dict[str, str] = game_names(rows=self.title_rows)
        self.port_rows: list[Port] = parse_ports(data=self._load_json(path=self.cache_dir / PORTS_FILE, default={}))
        self.ports_art_dir = self.base / "covers" / PORTS_ART_FOLDER
        self.mod_name = safe_name(name=registry.mod_name)
        self.download_dir = registry.download_dir
        self.upload_source = registry.upload_source
        self.upload_repo = registry.upload_repo
        self.upload_tag = registry.upload_tag
        self.auto_upload = registry.auto_upload
        self.auto_delete = self.auto_upload and registry.auto_delete
        self.upload_delete = registry.upload_delete
        # Settings from before this choice existed used the GitHub tab's repository.
        self.auto_repo = registry.auto_repo or self.upload_repo
        self.size_units = registry.size_units or BINARY
        self.notify = registry.notify
        self.ports_view = "grid" if registry.ports_view == "grid" else "list"
        self.catalog_view = "grid" if registry.catalog_view == "grid" else "list"
        self.font_family = registry.font_family
        self.font_size = registry.font_size
        # Desktop notifications waiting for the window, which takes them with take_notices.
        self.notices: list[Notice] = []
        set_size_units(units=self.size_units)
        self.compression = clean_compression(value=registry.compression)
        # SteamGridDB art: where the key is kept, the key once read (None until then), the cached
        # lookups by game name, and why lookups stopped. art_version changes with the key.
        self.art_key: StoredSecret = registry.art_key
        self.art_secret: str | None = None
        self.art_lookups_path = self.cache_dir / ART_LOOKUPS_FILE
        self.art_lookups: dict[str, ArtLookup] = self._load_model(
            path=self.art_lookups_path,
            schema=ART_LOOKUPS,
            default={},
        )
        self.art_error = ""
        self.art_paused_until = 0.0
        self.art_version = 0
        # Guards the art files and their index, written by several art threads.
        self.art_lock = threading.Lock()
        # SteamGridDB requests in flight, for the note at the foot of the window.
        self.art_active = 0
        self.release_error = ""
        self.catalogs: list[Catalog] = registry.catalogs
        active = next((c for c in self.catalogs if c.folder == registry.active), None)
        self._use_catalog(catalog=active or (self.catalogs[0] if self.catalogs else None))

    def _clear_failed_jobs(self) -> None:
        with self.lock:
            failed = [entry_id for entry_id, job in self.jobs.items() if job.phase == "error"]

            for entry_id in failed:
                del self.jobs[entry_id]

    def _use_catalog(self, catalog: Catalog | None) -> None:
        self._clear_failed_jobs()
        self.catalog: Catalog | None = catalog
        folder = catalog.folder if catalog else NO_CATALOG
        self.root = self._download_root() / folder
        self.art_dir = self.base / "covers" / folder
        self.state_path = self._catalog_file(folder=folder, name=STATE_FILE)
        self.cache_path = self._catalog_file(folder=folder, name=CATALOG_FILE)
        self.state: dict[str, DownloadRecord] = self._load_model(
            path=self.state_path,
            schema=DOWNLOAD_RECORDS,
            default={},
        )
        self.release_state = self._load_model(
            path=self._release_cache(folder=folder),
            schema=RELEASE_STATE,
            default=ReleaseState(),
        )
        self.items: list[Mod] = []
        self.checked_at = None
        self.check_error = None

        try:
            mapping = clean_mapping(mapping=catalog.mapping) if catalog else None
            document = parse_catalog(data=json.loads(s=self.cache_path.read_bytes()), mapping=mapping)
            self.items = self._named(items=document.items)
        except (OSError, ValueError):
            pass

    # A title ID shared by several entries, such as one game in two packs or two games in one
    # Switch title, would give them all one official name, so each keeps its catalog name.
    # Entries of the same file share one download, saved under the official name of the first,
    # else its catalog name.
    def _named(self, items: list[Mod]) -> list[Mod]:
        titles = collections.Counter(item.title_id.upper() for item in items if item.title_id)
        files: dict[str, list[Mod]] = {}

        for item in items:
            key = file_key(entry=item)

            if key:
                files.setdefault(key, []).append(item)

        named: list[Mod] = []

        for item in items:
            catalog_name = item.catalog_name or item.name
            title = item.title_id.upper()
            official = title_name(names=self.titles, title=title) if title else ""
            name = catalog_name if titles[title] > 1 else official or catalog_name
            group = files.get(file_key(entry=item), [item])
            first = group[0]
            first_name = first.catalog_name or first.name
            first_official = title_name(names=self.titles, title=first.title_id.upper())
            save_name = (first_official or first_name) if len(group) > 1 else name
            named.append(
                item.model_copy(
                    update={
                        "name": name,
                        "catalog_name": catalog_name,
                        "save_name": save_name,
                        "twins": [other.id for other in group if other.id != item.id],
                    },
                ),
            )

        return named

    # An entry and the ones that share its file, itself first.
    @staticmethod
    def _ids_of(entry: Mod) -> list[str]:
        return [entry.id, *entry.twins]

    # The entry, of those sharing a file with entry_id, that holds the running job, if any.
    def _job_owner(self, entry_id: str) -> str:
        with self.lock:
            entry = next((item for item in self.items if item.id == entry_id), None)
            ids = self._ids_of(entry=entry) if entry else [entry_id]

            return next((other for other in ids if other in self.jobs), entry_id)

    # The download record of an entry, or of another entry of the same file.
    def _record_of(self, entry: Mod) -> DownloadRecord | None:
        return next((self.state[other] for other in self._ids_of(entry=entry) if other in self.state), None)

    def _save_registry(self) -> None:
        registry = Registry(
            active=self.catalog.folder if self.catalog else None,
            catalogs=self.catalogs,
            mod_name=self.mod_name,
            download_dir=self.download_dir,
            upload_source=self.upload_source,
            upload_repo=self.upload_repo,
            upload_tag=self.upload_tag,
            auto_upload=self.auto_upload,
            auto_delete=self.auto_delete,
            upload_delete=self.upload_delete,
            auto_repo=self.auto_repo,
            size_units=self.size_units,
            notify=self.notify,
            ports_view=self.ports_view,
            catalog_view=self.catalog_view,
            font_family=self.font_family,
            font_size=self.font_size,
            compression=self.compression,
            art_key=self.art_key,
        )
        self._write_json(path=self.registry_path, value=registry)

    def _download_root(self) -> Path:
        return Path(self.download_dir).expanduser().resolve() if self.download_dir else self.base / DOWNLOAD_DIR

    # A catalog keeps its files in a folder of its own.
    def _catalog_file(self, folder: str, name: str) -> Path:
        return self.catalogs_dir / folder / name

    def _release_cache(self, folder: str) -> Path:
        return self._catalog_file(folder=folder, name=RELEASE_FILE)

    # gh gone or signed out leaves saved mods on disk, without a failed upload for each one.
    def _will_auto_upload(self) -> bool:
        return (
            self.auto_upload
            and self.gh_ready is not False
            and bool(uploader.releases.REPO_NAME.match(string=self.auto_repo))
        )

    @staticmethod
    def _load_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(s=path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    # A file this app wrote, checked against its schema. A missing, broken or mismatched one gives
    # the default, as a first run would.
    @classmethod
    def _load_model(cls, path: Path, schema: TypeAdapter[T], default: T) -> T:
        data = cls._load_json(path=path, default=None)

        if data is None:
            return default

        try:
            return schema.validate_python(data)
        except ValidationError:
            return default

    # Models are written as plain JSON, the same as the dicts they replaced.
    def _write_json(self, path: Path, value: object) -> None:
        text = json.dumps(obj=to_jsonable_python(value), ensure_ascii=False, indent=1)
        self._write_bytes(path=path, data=text.encode("utf-8"))

    def _write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(suffix=".tmp")
        temp.write_bytes(data)
        os.replace(src=temp, dst=path)

    @staticmethod
    def new_batch() -> Batch:
        return Batch(
            count=0,
            finished=0,
            total=0,
            passed=0,
            saved=0,
            failed=0,
            cancelled=0,
            uploaded=0,
            upload_failed=0,
            deleted=0,
        )
