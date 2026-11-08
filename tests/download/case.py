import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from nx_desk import names, net, vault
from nx_desk.schemas.catalog import Mod
from nx_desk.schemas.download import DownloadTask
from tests.helpers import mod


class DownloadCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.src = self.base / "src"
        self.dest = self.base / "out"
        self.src.mkdir()
        self.store = vault.Vault(base=self.base / "data")
        self.store.set_mod_name(name="VI")
        offline = mock.patch.object(net, "http_get", side_effect=OSError("offline"))
        offline.start()
        self.addCleanup(offline.stop)

    def zip_file(self, relative: str, members: dict[str, bytes]) -> Path:
        path = self.src / relative
        path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(file=path, mode="w") as output:
            for name, data in members.items():
                output.writestr(zinfo_or_arcname=name, data=data)

        return path

    def place(self, item: Mod, name: str = "[1.0-unreviewed] [VI].zip") -> Path:
        path = self.store.root / f"{item.name} - [VI]" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data=b"zip")

        return path

    def destination_item(self) -> Mod:
        self.store.set_download_dir(text=str(self.base / "mine"))

        return mod(name="Game", sha256="a" * 64, game_version="1.0")

    def run_worker(self, item: Mod) -> str:
        self.store.items = [item]
        self.store.enqueue(ids=[item.id])
        real_get = self.store.queue.get
        calls = iter([real_get])

        def next_entry() -> DownloadTask:
            step = next(calls, None)

            if step is None:
                raise SystemExit

            return step()

        with mock.patch.object(self.store.queue, "get", side_effect=next_entry), self.assertRaises(SystemExit):
            self.store.worker()

        if not self.store.repack_queue.empty():
            self.store._repack_next()

        return "\n".join(f"{game}: {text}" for _, _, game, text in self.store.snapshot().log)

    def run_worker_once(self) -> None:
        _, _, entry, cancel = self.store.queue.get()
        self.store._run_download(entry=entry, cancel=cancel)

    def log_text(self) -> str:
        return "\n".join(f"{game}: {text}" for _, _, game, text in self.store.snapshot().log)

    def queue_two(self, sizes: tuple[int, int] = (100, 300)) -> None:
        self.store.items = [mod(id=name, name=name, size=size) for name, size in zip("ab", sizes, strict=True)]
        self.store.enqueue(ids=["a", "b"])

    def save_download(self, item: Mod) -> Path:
        target = self.store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=target)

        return target
