import collections
import threading
from pathlib import Path
from typing import Callable, Optional, OrderedDict, Set

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from ...schemas.artwork import ArtFiles
from .layout import MAX_COVER

# Thumbnails kept in memory (about 330 KB each) and decoded at once; a request that no longer matters is dropped.
KEPT = 150
THREADS = 2
MOST_WAITING = 60


# The cover of a card, cut to fill the biggest cover a card can have, from art files on disk. Decoding an image
# and shrinking it takes tens of milliseconds, so it happens on two threads; the UI asks again until the
# thumbnail is ready, newest request first, since that is what is in view. Where the files are, when the
# cache must start over and when an entry is known to have no art are told by the tab that owns the art.
class CoverThumbs:
    def __init__(
        self,
        files: Callable[[str], Optional[ArtFiles]],
        version: Callable[[], object],
        settled: Callable[[str], bool],
    ) -> None:
        self.files = files
        self.current = version
        self.settled = settled
        self.version = version()
        self.lock = threading.Lock()
        self.images: OrderedDict[str, QImage] = collections.OrderedDict()
        self.waiting: OrderedDict[str, Path] = collections.OrderedDict()
        self.failed: Set[str] = set()
        self.workers = 0
        # Counts the thumbnails built, so a view knows when to draw again.
        self.ready = 0

    # The art file of an entry that has some, else None.
    def source(self, key: str) -> Optional[Path]:
        files = self.files(key)

        return (files.cover or files.background) if files else None

    # An entry that was looked up and has no art, or whose art cannot be read: it shows an icon.
    def shows_icon(self, key: str) -> bool:
        bare = self.settled(key) and self.source(key=key) is None

        with self.lock:
            return bare or key in self.failed

    # The thumbnail if it is ready; otherwise None, and it is made in the background.
    def get(self, key: str) -> Optional[QImage]:
        version = self.current()
        path = self.source(key=key)

        with self.lock:
            if self.version != version:
                self.version = version
                self.images.clear()
                self.waiting.clear()
                self.failed.clear()

            if key in self.images:
                self.images.move_to_end(key)

                return self.images[key]

            if path is None or key in self.failed or key in self.waiting:
                return None

            self.waiting[key] = path

            while len(self.waiting) > MOST_WAITING:
                self.waiting.popitem(last=False)

            start = self.workers < THREADS
            self.workers += start

        if start:
            threading.Thread(target=self.work, args=(version,), daemon=True).start()

        return None

    # Runs on a thread: only the disk and QImage, which may be used away from the UI thread.
    def work(self, version: object) -> None:
        while True:
            with self.lock:
                if not self.waiting or version != self.version:
                    self.workers -= 1

                    return

                key, path = self.waiting.popitem(last=True)

            image = self.build(path=path)

            with self.lock:
                if version != self.version:
                    continue

                if image is None:
                    self.failed.add(key)

                else:
                    self.images[key] = image
                    self.ready += 1

                    while len(self.images) > KEPT:
                        self.images.popitem(last=False)

    @staticmethod
    def build(path: Path) -> Optional[QImage]:
        image = QImage(str(path))

        if image.isNull():
            return None

        width, height = MAX_COVER
        scaled = image.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        cut = scaled.copy((scaled.width() - width) // 2, (scaled.height() - height) // 2, width, height)

        return cut.convertToFormat(QImage.Format.Format_RGB32)
