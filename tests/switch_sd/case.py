import tempfile
import threading
import unittest
from pathlib import Path

from nx_desk.schemas.switch_sd import MountedVolume
from nx_desk.switch_sd import detect

TITLE = "010000000000A000"
OTHER = "010000000000B000"


class SDCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.root = self.base / "card"
        (self.root / "atmosphere").mkdir(parents=True)
        (self.root / "atmosphere" / "package3").write_bytes(data=b"synthetic-firmware")
        self.volume = MountedVolume(root=self.root, filesystem="exfat", label="Synthetic card", device="synthetic")
        card = detect.detect(volume=self.volume)
        assert card is not None
        self.card = card
        self.cancel = threading.Event()

    def put(self, relative: str, data: bytes = b"old") -> Path:
        path = self.root / "atmosphere" / "contents" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data=data)

        return path
