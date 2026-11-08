import threading
from pathlib import Path
from typing import TYPE_CHECKING

from ..catalog.ports import card_url
from ..config import ART_WORKERS
from ..schemas.port import Port

if TYPE_CHECKING:
    from . import Vault


# Fetches the art of the entries a tab asks for, from SteamGridDB only, with no toolkit: the tab names the
# entries it wants, the chosen one first, and a few threads take them in order. A new list of wanted
# entries drops those still waiting, so a list of hundreds does not spend the key's rate limit at once.
class ArtQueue:
    def __init__(self, vault: "Vault") -> None:
        self.vault = vault
        self.version = vault.art_version
        self.lock = threading.Lock()
        # Art files by entry id, filled by the art threads.
        self.files: dict[str, tuple[Path | None, Path | None]] = {}
        self.asked: set[str] = set()
        self.waiting: list[Port] = []
        self.workers = 0

    def needs_key(self) -> bool:
        return not self.vault.has_art_key()

    # No art to wait for: there is no key, or the entry was looked up and has none.
    def settled(self, port: Port) -> bool:
        return self.needs_key() or port.id in self.files

    # A new or removed key brings other art, so everything found so far is dropped.
    def check_key(self) -> None:
        if self.version != self.vault.art_version:
            with self.lock:
                self.version = self.vault.art_version
                self.files = {}
                self.asked = set()
                self.waiting = []

    def want(self, ports: list[Port]) -> None:
        self.check_key()

        if self.needs_key():
            return

        with self.lock:
            self.waiting = [port for port in ports if port.id not in self.asked and port.id not in self.files]
            start = min(ART_WORKERS, len(self.waiting)) - self.workers
            self.workers += max(0, start)
            version = self.version

        for _ in range(max(0, start)):
            threading.Thread(target=self.work, args=(version,), daemon=True).start()

    # Runs on an art thread: only the network and the disk.
    def work(self, version: int) -> None:
        while True:
            with self.lock:
                if version != self.version or not self.waiting:
                    self.workers -= 1

                    return

                port = self.waiting.pop(0)
                self.asked.add(port.id)

            self.fetch(port=port, version=version)

    def fetch(self, port: Port, version: int) -> None:
        urls = self.vault.steamgrid_art(item=port)

        if urls is None:
            # Not answered (a pause or no network), so wanting the entry again asks again.
            with self.lock:
                self.asked.discard(port.id)

            return

        art_dir = self.vault.ports_art_dir
        cover = self.vault.fetch_art(item=port, kind="cover", url=urls[0], art_dir=art_dir)
        background = self.vault.fetch_art(item=port, kind="background", url=urls[1], art_dir=art_dir)

        # SteamGridDB knew nothing of it, so a GitHub repository gets the card GitHub draws for it.
        if not urls[0] and not urls[1]:
            background = self.vault.fetch_art(item=port, kind="background", url=card_url(port=port), art_dir=art_dir)

        if version == self.version:
            self.files[port.id] = (cover, background)
