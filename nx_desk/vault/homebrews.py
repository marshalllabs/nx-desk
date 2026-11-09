import http.client
import time
from typing import List

from .. import config as settings
from .. import net
from ..catalog.homebrews import parse_homebrews
from ..config import HOMEBREWS_FILE, HOMEBREWS_KEY, HOMEBREWS_MAX_AGE, MAX_CATALOG
from ..schemas.homebrew import Homebrew, HomebrewSnapshot
from ..utils.json import parse_json
from .artwork import Artwork


class Homebrews(Artwork):
    def _keep_homebrews(self, rows: List[Homebrew]) -> None:
        if rows:
            with self.lock:
                self.homebrew_rows = rows
                self.homebrew_version += 1

    def load_homebrews(self, force: bool = False) -> None:
        with self.lock:
            if self.homebrew_loading:
                return

            self.homebrew_loading = True
            self.homebrew_error = ""

        path = self.cache_dir / HOMEBREWS_FILE
        error = ""

        try:
            self._keep_homebrews(rows=parse_homebrews(data=self._load_json(path=path, default={})))
            url = settings.load_config().get(HOMEBREWS_KEY, "")

            if not url.startswith("https://"):
                raise ValueError("The Homebrews feed is not configured")

            if force or not self.homebrew_rows or time.time() - path.stat().st_mtime >= HOMEBREWS_MAX_AGE:
                with net.http_get(url=url, timeout=60) as response:
                    raw = response.read(MAX_CATALOG + 1)

                if len(raw) > MAX_CATALOG:
                    raise ValueError("The Homebrews list is too large")

                rows = parse_homebrews(data=parse_json(text=raw))

                if not rows:
                    raise ValueError("The Homebrews list is empty")

                self._write_bytes(path=path, data=raw)
                self._keep_homebrews(rows=rows)
                self.prune_art(items=rows, art_dir=self.homebrews_art_dir)

        except (OSError, ValueError, http.client.HTTPException) as found:
            error = str(found) or type(found).__name__

        finally:
            with self.lock:
                self.homebrew_loading = False
                self.homebrew_error = error

    def homebrew_snapshot(self) -> HomebrewSnapshot:
        with self.lock:
            return HomebrewSnapshot(
                rows=list(self.homebrew_rows),
                version=self.homebrew_version,
                loading=self.homebrew_loading,
                error=self.homebrew_error,
            )
