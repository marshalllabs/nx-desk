import queue
import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...config import ART_WORKERS
from ...schemas.snapshot import ModRow
from ..art import banner_from_files
from .state import CatalogTabState


class ArtPane(CatalogTabState):
    def show_art(self, item: ModRow) -> None:
        if self.art_id == item.id:
            return

        key = (self.vault.root.name, item.id)

        if key not in self.art_cache and key in self.art_files:
            self.art_cache[key] = self.make_banner(*self.art_files[key])

        image = self.art_cache.get(key)

        if image is None:
            return

        self.art_id = item.id
        self.art_image = image
        self.fit_art()
        self.art.show()

    # The banner fills the pane's width at its own aspect, so dragging the pane wider leaves no gap.
    def fit_art(self) -> None:
        if self.art_image is None:
            return

        width = max(1, self.detail_scroll.viewport().width())
        height = round(width * self.ART_SIZE[1] / self.ART_SIZE[0])
        picture = QPixmap.fromImage(self.art_image).scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.art.setPixmap(picture)
        self.art.setFixedHeight(picture.height())

    # What the grid's thumbnails ask of the art: the files of a game, when to start over, who has none.
    def thumb_files(self, key: str) -> tuple[Path | None, Path | None] | None:
        return self.art_files.get((self.vault.root.name, key))

    def thumb_version(self) -> tuple[int, str]:
        return self.vault.art_version, self.vault.root.name

    # A game with no art file is known to have none once every art thread has ended.
    def thumb_settled(self, key: str) -> bool:
        return not any(thread.is_alive() for thread in self.art_threads)

    def thumb_changes(self) -> tuple[int, int]:
        return len(self.art_files), self.vault.art_version

    def preload_art(self) -> None:
        vault = self.vault
        keyed = vault.has_art_key()
        # With a SteamGridDB key, games without catalog art may still find some.
        items = [item for item in self.items.values() if keyed or item.cover or item.background]
        signature = (vault.root.name, vault.art_version, *((item.id, item.cover, item.background) for item in items))

        if signature == self.art_signature:
            return

        # A new key brings other art, so the banners drawn so far are dropped.
        if self.art_signature is not None and self.art_signature[1] != vault.art_version:
            self.art_cache.clear()
            self.art_files.clear()
            self.art_id = None

        self.art_signature = signature
        art_dir = vault.art_dir
        vault.prune_art(items=list(self.items.values()), art_dir=art_dir)
        pending: queue.Queue[ModRow] = queue.Queue()

        # The chosen game first, so its banner does not wait for the whole list.
        for item in sorted(items, key=lambda item: item.id != self.selected):
            pending.put(item=item)

        self.art_threads = [thread for thread in self.art_threads if thread.is_alive()]

        for _ in range(ART_WORKERS):
            thread = threading.Thread(target=self.art_worker, args=(pending, art_dir), daemon=True)

            thread.start()
            self.art_threads.append(thread)

    # Runs on an art thread: only the network and the disk, no Qt.
    def art_worker(self, pending: queue.Queue[ModRow], art_dir: Path) -> None:
        while True:
            try:
                item = pending.get_nowait()
            except queue.Empty:
                return

            cover_url, background_url = self.vault.art_sources(item=item)
            cover = self.vault.fetch_art(item=item, kind="cover", url=cover_url, art_dir=art_dir)
            background = self.vault.fetch_art(item=item, kind="background", url=background_url, art_dir=art_dir)

            if cover or background:
                self.art_files[(art_dir.name, item.id)] = (cover, background)

    # Qt crashed when several threads painted at once, so banners are drawn here, on the UI thread,
    # once each and only when a game is shown.
    def make_banner(self, cover_path: Path | None, background_path: Path | None) -> QImage | None:
        return banner_from_files(cover_path=cover_path, background_path=background_path)
