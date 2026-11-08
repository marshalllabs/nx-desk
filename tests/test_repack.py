import random
import tempfile
import threading
import time
import unittest
import zipfile
import zlib
from collections.abc import Iterable
from pathlib import Path
from unittest import mock

from nx_desk import config as settings
from nx_desk import vault, zips
from nx_desk.schemas.catalog import Mod
from nx_desk.schemas.download import Fetched
from tests.helpers import TITLE, mod


class RepackTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def zip_with(self, names: Iterable[str]) -> Path:
        path = self.dir / "source.zip"

        with zipfile.ZipFile(file=path, mode="w") as output:
            for name in names:
                output.writestr(zinfo_or_arcname=name, data=b"data " + name.encode() * 50)

        return path

    def repacked(self, names: Iterable[str]) -> zipfile.ZipFile:
        target = self.dir / "out.zip"
        zips.repack(source=self.zip_with(names=names), target=target, title_id=TITLE)

        return zipfile.ZipFile(file=target)

    def test_layouts_all_become_contents_title_id(self) -> None:
        for prefix in ("atmosphere/contents/", "atmosphere\\contents\\", "Wrapper/atmosphere/contents/", "Wrapper/"):
            with self.subTest(prefix=prefix):
                sep = "\\" if "\\" in prefix else "/"
                result = self.repacked(names=[f"{prefix}{TITLE}{sep}romfs{sep}a.bin"])
                self.assertEqual(
                    result.namelist(),
                    ["contents/", f"contents/{TITLE}/", f"contents/{TITLE}/romfs/", f"contents/{TITLE}/romfs/a.bin"],
                )

    def test_files_use_deflate_and_keep_content(self) -> None:
        result = self.repacked(names=[f"{TITLE}/romfs/a.bin"])
        info = result.getinfo(name=f"contents/{TITLE}/romfs/a.bin")
        self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
        self.assertTrue(result.read(info).startswith(b"data "))

    def test_ignores_instructions_and_junk(self) -> None:
        result = self.repacked(names=[f"{TITLE}/romfs/a", "HUONG_DAN.txt", "__MACOSX/x", f"{TITLE}/.DS_Store"])
        self.assertEqual([n for n in result.namelist() if not n.endswith("/")], [f"contents/{TITLE}/romfs/a"])

    def test_rejects_unexpected_layouts(self) -> None:
        cases = {
            "traversal": [f"{TITLE}/../../evil"],
            "other title": ["0100000000000001/romfs/a"],
            "stray file": ["romfs/a.bin"],
            "nothing": ["x.txt"],
            "case clash": [f"a/{TITLE}/romfs/F", f"b/{TITLE}/romfs/f"],
        }

        for name, members in cases.items():
            with self.subTest(name):
                target = self.dir / "out.zip"

                with self.assertRaises(RuntimeError):
                    zips.repack(source=self.zip_with(names=members), target=target, title_id=TITLE)

                self.assertFalse(target.exists())


class DeflateTests(unittest.TestCase):
    def test_uses_deflate_level_nine(self) -> None:
        words = random.Random(x=1).choices(population=["alpha", "beta", "gamma", "delta", "omega", "sigma"], k=60000)
        data = " ".join(words).encode()

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.zip"
            target = Path(folder) / "target.zip"

            with zipfile.ZipFile(file=source, mode="w") as output:
                output.writestr(zinfo_or_arcname=f"{TITLE}/romfs/a.bin", data=data)

            zips.repack(source=source, target=target, title_id=TITLE)

            with zipfile.ZipFile(file=target) as archive:
                info = archive.getinfo(name=f"contents/{TITLE}/romfs/a.bin")

        packer = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
        self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
        self.assertEqual(info.compress_size, len(packer.compress(data) + packer.flush()))


class CompressionTests(unittest.TestCase):
    def test_each_level_keeps_the_files_and_compression_shrinks_them(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "source.zip"
            body = b"".join(str(number).encode() for number in range(200000))

            with zipfile.ZipFile(file=source, mode="w") as output:
                output.writestr(zinfo_or_arcname=f"{TITLE}/romfs/a.bin", data=body)

            sizes = []

            for _, level in settings.COMPRESSION_LEVELS:
                target = base / f"{level}.zip"
                zips.repack(source=source, target=target, title_id=TITLE, level=level)

                with zipfile.ZipFile(file=target) as archive:
                    self.assertEqual(archive.read(f"contents/{TITLE}/romfs/a.bin"), body)

                sizes.append(target.stat().st_size)

            self.assertEqual(max(sizes), sizes[0])
            self.assertLess(sizes[-1], sizes[0] / 2)


class RepackQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.store = vault.Vault(base=self.base)
        self.store.mod_name = "VI"

    def queued(self, name: str = "Game", size: int = 0) -> Path:
        source = self.base / f"{name}.zip"

        with zipfile.ZipFile(file=source, mode="w") as output:
            output.writestr(zinfo_or_arcname=f"{TITLE}/romfs/a.bin", data=b"data" * 4000)

        item: Mod = mod(id=name.lower(), name=name, sha256="").model_copy(update={"size": size})

        self.store.items.append(item)
        self.store.enqueue(ids=[item.id])

        return source

    def download(self, source: Path) -> Mod:
        _, _, item, cancel = self.store.queue.get()

        with mock.patch.object(self.store, "_download", return_value=Fetched(wire=source)):
            self.store._run_download(entry=item, cancel=cancel)

        return item

    def test_a_finished_download_waits_for_repacking_without_its_slot(self) -> None:
        item = self.download(source=self.queued())
        self.assertEqual(self.store.jobs[item.id].phase, "waiting_repack")
        self.assertTrue(self.store.busy())
        self.assertEqual(list(self.store.root.rglob(pattern="*.zip")), [])
        self.store._repack_next()
        self.assertFalse(self.store.busy())
        self.assertEqual(self.store.status_of(entry=item), "ok")

    def test_a_slow_repack_does_not_hold_up_the_next_download(self) -> None:
        first, second = self.queued(name="First", size=1000), self.queued(name="Second", size=2000)
        repacking, release = threading.Event(), threading.Event()

        def slow(*_: object, **__: object) -> None:

            repacking.set()
            release.wait(timeout=5)

        with (
            mock.patch.object(self.store, "_download", side_effect=[Fetched(wire=first), Fetched(wire=second)]),
            mock.patch.object(zips, "repack", side_effect=slow),
        ):
            threading.Thread(target=self.store.worker, daemon=True).start()
            threading.Thread(target=self.store.repack_worker, daemon=True).start()
            self.assertTrue(repacking.wait(timeout=5))
            deadline = time.monotonic() + 5

            while self.store.jobs["second"].phase != "waiting_repack" and time.monotonic() < deadline:
                time.sleep(0.01)

            self.assertEqual(self.store.jobs["first"].phase, "repacking")
            self.assertEqual(self.store.jobs["second"].phase, "waiting_repack")
            release.set()
            # The workers write state and logs while finishing, so they end before the folder goes.
            deadline = time.monotonic() + 5

            while self.store.busy() and time.monotonic() < deadline:
                time.sleep(0.01)

            self.assertFalse(self.store.busy())

    def test_the_smallest_download_repacks_first(self) -> None:
        large, small = self.queued(name="Large", size=2000), self.queued(name="Small", size=1000)
        self.download(source=small)
        self.download(source=large)
        self.assertEqual(self.store.repack_queue.get()[2].id, "small")

    def test_a_stopped_download_is_not_repacked_and_keeps_its_file(self) -> None:
        source = self.queued()
        item = self.download(source=source)
        self.store.cancel(entry_id=item.id)

        with mock.patch.object(zips, "repack") as repack:
            self.store._repack_next()

        repack.assert_not_called()
        self.assertTrue(source.exists())

    def test_a_failed_repack_is_reported_on_the_job(self) -> None:
        item = self.download(source=self.queued())

        with mock.patch.object(zips, "repack", side_effect=RuntimeError("bad zip")):
            self.store._repack_next()

        self.assertEqual(self.store.jobs[item.id].phase, "error")
        self.assertEqual(self.store.batch.failed, 1)

    def test_the_chosen_level_is_used_and_remembered(self) -> None:
        self.store.set_compression(level=0)
        item = self.download(source=self.queued())
        self.store._repack_next()
        target = next(self.store.root.rglob(pattern="*.zip"))

        with zipfile.ZipFile(file=target) as archive:
            member = next(info for info in archive.infolist() if info.filename.endswith("a.bin"))

        self.assertEqual(member.compress_type, zipfile.ZIP_STORED)
        self.assertEqual(vault.Vault(base=self.base).compression, 0)
        self.assertEqual(self.store.status_of(entry=item), "ok")

    def test_an_unknown_level_falls_back(self) -> None:
        for value in (5, "9", None, True):
            self.assertEqual(settings.clean_compression(value=value), settings.DEFAULT_COMPRESSION)
