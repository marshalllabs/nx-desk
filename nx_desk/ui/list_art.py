from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QImage

from ..schemas.artwork import ArtSubject
from ..vault.art_queue import ArtQueue
from .art import banner_from_files, placeholder_image
from .cards.thumbs import Files

if TYPE_CHECKING:
    from ..vault import Vault

# Banners kept in memory; one is about 1.3 MB, and only the entry in front is drawn.
KEPT_BANNERS = 24


# The art of the entries on screen: the queue fetches the files, and this draws them on the UI thread.
class ListArt:
    def __init__(self, vault: "Vault", art_dir: Path, port_cards: bool = False) -> None:
        self.queue = ArtQueue(vault=vault, art_dir=art_dir, port_cards=port_cards)
        self.version = self.queue.version
        self.banners: dict[str, QImage | None] = {}
        self.placeholders: dict[str, QImage] = {}

    def needs_key(self) -> bool:
        return self.queue.needs_key()

    def settled(self, item: ArtSubject) -> bool:
        return self.queue.settled(item=item)

    # What the grid's thumbnails ask of the art: the files of an entry, when to start over, who has none.
    def files_of(self, key: str) -> Files | None:
        return self.queue.files.get(key)

    def version_of(self) -> int:
        self.queue.check_key()

        return self.queue.version

    def settled_key(self, key: str) -> bool:
        return self.queue.needs_key() or key in self.queue.files

    def changes(self) -> int:
        return len(self.queue.files)

    def want(self, items: Sequence[ArtSubject]) -> None:
        self.queue.want(items=items)

    def placeholder(self, icon_name: str) -> QImage:

        if icon_name not in self.placeholders:
            self.placeholders[icon_name] = placeholder_image(icon_name=icon_name)

        return self.placeholders[icon_name]

    # On the UI thread, because Qt crashed when several threads painted at once.
    def banner(self, item: ArtSubject) -> QImage | None:
        self.queue.check_key()

        if self.version != self.queue.version:
            self.version = self.queue.version
            self.banners = {}

        if item.id in self.banners:
            return self.banners[item.id]

        files = self.queue.files.get(item.id)

        if files is None:
            return None

        image = banner_from_files(cover_path=files[0], background_path=files[1])
        self.banners[item.id] = image

        while len(self.banners) > KEPT_BANNERS:
            del self.banners[next(iter(self.banners))]

        return image
