from typing import TYPE_CHECKING

from PySide6.QtGui import QImage

from ...schemas.port import Port
from ...vault.art_queue import ArtQueue
from ..art import banner_from_files, placeholder_image
from ..cards.thumbs import Files

if TYPE_CHECKING:
    from ...vault import Vault

# Banners kept in memory; one is about 1.3 MB, and only the entry in front is drawn.
KEPT_BANNERS = 24


# The art of the entries on screen: the queue fetches the files, and this draws them on the UI thread.
class PortArt:
    def __init__(self, vault: "Vault") -> None:
        self.queue = ArtQueue(vault=vault)
        self.version = self.queue.version
        self.banners: dict[str, QImage | None] = {}
        self.placeholders: dict[str, QImage] = {}

    def needs_key(self) -> bool:
        return self.queue.needs_key()

    def settled(self, port: Port) -> bool:
        return self.queue.settled(port=port)

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

    def want(self, ports: list[Port]) -> None:
        self.queue.want(ports=ports)

    def placeholder(self, port: Port) -> QImage:
        icon_name = "cpu" if port.kind == "emulator" else "gamepad"

        if icon_name not in self.placeholders:
            self.placeholders[icon_name] = placeholder_image(icon_name=icon_name)

        return self.placeholders[icon_name]

    # On the UI thread, because Qt crashed when several threads painted at once.
    def banner(self, port: Port) -> QImage | None:
        self.queue.check_key()

        if self.version != self.queue.version:
            self.version = self.queue.version
            self.banners = {}

        if port.id in self.banners:
            return self.banners[port.id]

        files = self.queue.files.get(port.id)

        if files is None:
            return None

        image = banner_from_files(cover_path=files[0], background_path=files[1])
        self.banners[port.id] = image

        while len(self.banners) > KEPT_BANNERS:
            del self.banners[next(iter(self.banners))]

        return image
