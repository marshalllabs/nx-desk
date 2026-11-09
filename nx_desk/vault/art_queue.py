import threading
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence, Set

from ..catalog.ports import card_url
from ..config import ART_WORKERS
from ..schemas.artwork import ArtFiles, ArtSources, ArtSubject
from ..schemas.catalog import ArtKind
from ..schemas.port import Port


class ArtProvider(Protocol):
    art_version: int
    ports_art_dir: Path

    def has_art_key(self) -> bool: ...

    def steamgrid_art(self, item: ArtSubject) -> Optional[ArtSources]: ...

    def fetch_art(self, item: ArtSubject, kind: ArtKind, url: str, art_dir: Path) -> Optional[Path]: ...


# Fetches the art of the entries a tab asks for, from SteamGridDB only, with no toolkit: the tab names the
# entries it wants, the chosen one first, and a few threads take them in order. A new list of wanted
# entries drops those still waiting, so a list of hundreds does not spend the key's rate limit at once.
class ArtQueue:
    def __init__(self, vault: ArtProvider, art_dir: Optional[Path] = None, port_cards: bool = True) -> None:
        self.vault = vault
        self.art_dir = art_dir if art_dir is not None else vault.ports_art_dir
        self.port_cards = port_cards
        self.version = vault.art_version
        self.lock = threading.Lock()
        # Art files by entry id, filled by the art threads.
        self.files: Dict[str, ArtFiles] = {}
        self.asked: Set[str] = set()
        self.waiting: List[ArtSubject] = []
        self.workers = 0

    def needs_key(self) -> bool:
        return not self.vault.has_art_key()

    # No art to wait for: there is no key, or the entry was looked up and has none.
    def settled(self, item: ArtSubject) -> bool:
        return self.needs_key() or item.id in self.files

    # A new or removed key brings other art, so everything found so far is dropped.
    def check_key(self) -> None:
        if self.version != self.vault.art_version:
            with self.lock:
                self.version = self.vault.art_version
                self.files = {}
                self.asked = set()
                self.waiting = []

    def want(self, items: Sequence[ArtSubject]) -> None:
        self.check_key()

        if self.needs_key():
            return

        with self.lock:
            self.waiting = [item for item in items if item.id not in self.asked and item.id not in self.files]
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

                item = self.waiting.pop(0)
                self.asked.add(item.id)

            self.fetch(item=item, version=version)

    def fetch(self, item: ArtSubject, version: int) -> None:
        urls = self.vault.steamgrid_art(item=item)

        if urls is None:
            # Not answered (a pause or no network), so wanting the entry again asks again.
            with self.lock:
                self.asked.discard(item.id)

            return

        art_dir = self.art_dir
        cover = self.vault.fetch_art(item=item, kind="cover", url=urls.cover, art_dir=art_dir)
        background = self.vault.fetch_art(item=item, kind="background", url=urls.background, art_dir=art_dir)

        # SteamGridDB knew nothing of it, so a GitHub repository gets the card GitHub draws for it.
        if not urls.cover and not urls.background and self.port_cards and isinstance(item, Port):
            background = self.vault.fetch_art(item=item, kind="background", url=card_url(port=item), art_dir=art_dir)

        if version == self.version:
            self.files[item.id] = ArtFiles(cover=cover, background=background)
