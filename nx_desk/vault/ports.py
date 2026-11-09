import http.client
import time
from typing import List

from .. import config as settings
from .. import net
from ..catalog.ports import parse_ports
from ..config import MAX_CATALOG, PORTS_FILE, PORTS_KEY, PORTS_MAX_AGE
from ..schemas.port import Port, PortSnapshot
from ..utils.json import parse_json
from .artwork import Artwork


class Ports(Artwork):
    def _keep_port_rows(self, rows: List[Port]) -> None:
        if rows:
            with self.lock:
                self.port_rows = rows
                self.port_version += 1

    # The cached list shows at once; a failed refresh leaves it in place and only reports why.
    def load_ports(self, force: bool = False) -> None:
        with self.lock:
            if self.port_loading:
                return

            self.port_loading = True
            self.port_error = ""

        path = self.cache_dir / PORTS_FILE
        error = ""

        try:
            self._keep_port_rows(rows=parse_ports(data=self._load_json(path=path, default={})))
            url = settings.load_config().get(PORTS_KEY, "")

            if not url.startswith("https://"):
                raise ValueError(f"Set {PORTS_KEY} to the HTTPS link of switch-ports.json")

            if force or not self.port_rows or time.time() - path.stat().st_mtime >= PORTS_MAX_AGE:
                with net.http_get(url=url, timeout=60) as response:
                    raw = response.read(MAX_CATALOG + 1)

                if len(raw) > MAX_CATALOG:
                    raise ValueError("the ports list is too large")

                rows = parse_ports(data=parse_json(text=raw))

                if not rows:
                    raise ValueError("the ports list is empty")

                self._write_bytes(path=path, data=raw)
                self._keep_port_rows(rows=rows)
                # Art of entries that left the list goes with them.
                self.prune_art(items=rows, art_dir=self.ports_art_dir)

        except (OSError, ValueError, http.client.HTTPException) as error_found:
            error = str(error_found) or type(error_found).__name__

        with self.lock:
            self.port_loading = False
            self.port_error = error

    def port_snapshot(self) -> PortSnapshot:
        with self.lock:
            return PortSnapshot(
                rows=self.port_rows,
                version=self.port_version,
                loading=self.port_loading,
                error=self.port_error,
            )
