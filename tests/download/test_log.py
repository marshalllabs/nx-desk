import threading
from unittest import mock

from nx_desk import config as settings
from nx_desk.schemas.download import Fetched
from tests.download.case import DownloadCase
from tests.helpers import TITLE, mod


class DownloadLogTests(DownloadCase):
    def test_download_log_follows_a_download(self) -> None:
        self.zip_file(relative="Game.zip", members={f"{TITLE}/romfs/a.bin": b"1"})
        item = mod(name="Game", sha256="")

        with mock.patch.object(
            target=self.store,
            attribute="_download",
            return_value=Fetched(wire=self.src / "Game.zip"),
        ):
            text = self.run_worker(item=item)

        for expected in ("queued", "starting", "repacking", "saved"):
            self.assertIn(member=expected, container=text)

    def test_download_log_keeps_retries_and_the_failure(self) -> None:
        item = mod(name="Game", sha256="a" * 64)

        with mock.patch.object(target=threading.Event, attribute="wait", return_value=False):
            text = self.run_worker(item=item)

        self.assertEqual(first=text.count("download error"), second=settings.RETRIES)
        self.assertIn(member="Game: error: offline", container=text)

    def test_logs_use_the_clean_game_name(self) -> None:
        self.store.items = [mod(name="Game: It's")]
        self.store.enqueue(ids=["game"])
        line = self.store.snapshot().log[-1]
        game, text = line.game, line.text
        self.assertEqual(first=game, second="Game Its")
        self.assertTrue(expr=text.startswith("queued"))

    def test_download_log_marks_saved_files(self) -> None:
        self.zip_file(relative="Game.zip", members={f"{TITLE}/romfs/a.bin": b"1"})

        with mock.patch.object(
            target=self.store,
            attribute="_download",
            return_value=Fetched(wire=self.src / "Game.zip"),
        ):
            self.run_worker(item=mod(name="Game", sha256=""))

        self.assertEqual(first=self.store.snapshot().log[-1].level, second="ok")
