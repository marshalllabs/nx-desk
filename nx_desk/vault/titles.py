import http.client
import json
import time

from .. import config as settings
from .. import net
from ..catalog.title_ids import game_names, parse_title_ids
from ..config import (
    MAX_CATALOG,
    TITLE_IDS_FILE,
    TITLE_IDS_KEY,
    TITLE_IDS_MAX_AGE,
)
from ..schemas.title import TitleRow, TitleSnapshot
from .base import VaultBase


class Titles(VaultBase):
    # Names come from the title ID list. Without it, games keep their catalog names.
    def title_names(self) -> dict[str, str]:
        self.load_title_ids()

        with self.lock:
            return game_names(rows=self.title_rows)

    def _keep_title_rows(self, rows: list[TitleRow]) -> None:
        if rows:
            with self.lock:
                self.title_rows = rows
                self.title_version += 1

    # The cached list shows at once; a failed refresh leaves it in place and only reports why.
    def load_title_ids(self, force: bool = False) -> None:
        with self.lock:
            if self.title_loading:
                return

            self.title_loading = True
            self.title_error = ""

        path = self.cache_dir / TITLE_IDS_FILE
        error = ""

        try:
            self._keep_title_rows(rows=parse_title_ids(data=self._load_json(path=path, default={})))
            url = settings.load_config().get(TITLE_IDS_KEY, "")

            if not url.startswith("https://"):
                raise ValueError(f"Set {TITLE_IDS_KEY} to the HTTPS link of title-ids.json")

            if force or not self.title_rows or time.time() - path.stat().st_mtime >= TITLE_IDS_MAX_AGE:
                with net.http_get(url=url, timeout=60) as response:
                    raw = response.read(MAX_CATALOG + 1)

                if len(raw) > MAX_CATALOG:
                    raise ValueError("the title ID list is too large")

                rows = parse_title_ids(data=json.loads(s=raw))

                if not rows:
                    raise ValueError("the title ID list is empty")

                self._write_bytes(path=path, data=raw)
                self._keep_title_rows(rows=rows)
        except (OSError, ValueError, http.client.HTTPException) as error_found:
            error = str(error_found) or type(error_found).__name__

        with self.lock:
            self.title_loading = False
            self.title_error = error

    def title_snapshot(self) -> TitleSnapshot:
        with self.lock:
            return TitleSnapshot(
                rows=self.title_rows,
                version=self.title_version,
                loading=self.title_loading,
                error=self.title_error,
            )

    def refresh_titles(self) -> dict[str, str]:
        names = self.title_names()

        with self.lock:
            if names != self.titles:
                self.titles = names
                self.items = self._named(items=self.items)

        return names
