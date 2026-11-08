import threading
import time
from unittest import mock

from nx_desk import net
from nx_desk.schemas.download import Fetched
from tests.download.case import DownloadCase
from tests.helpers import TITLE, mod


class QueueTests(DownloadCase):
    def test_mods_go_in_by_size_whatever_order_they_are_chosen_in(self) -> None:
        self.store.items = [
            mod(id="big", size=83, sha256="a" * 64, url="https://example.com/big.zip"),
            mod(id="small", size=19, sha256="b" * 64, url="https://example.com/small.zip"),
            mod(id="mid", size=30, sha256="c" * 64, url="https://example.com/mid.zip"),
        ]
        order: list[str] = []

        # An idle worker takes each mod as it is put, so the order they are put in is the order they start.
        with mock.patch.object(self.store.queue, "put", lambda item: order.append(item[2].id)):
            self.store.enqueue(ids=["big", "small", "mid"])

        self.assertEqual(order, ["small", "mid", "big"])

    def test_stop_all_cancels_every_download(self) -> None:
        items = [mod(id=name, name=name) for name in ("a", "b")]
        self.store.items = items
        self.store.enqueue(ids=["a", "b"])
        events = list(self.store.cancels.values())
        self.store.cancel_all()
        self.assertTrue(all(event.is_set() for event in events))
        self.assertEqual((self.store.jobs, self.store.cancels), ({}, {}))
        self.assertFalse(self.store.busy())
        self.assertEqual(self.store.batch_progress().cancelled, 2)

    def test_stop_all_wakes_a_download_that_waits_on_the_server(self) -> None:
        item = mod(name="Game", sha256="")
        item.size = 10
        self.store.items = [item]
        self.store.enqueue(ids=[item.id])
        waiting, woke = threading.Event(), threading.Event()

        class Stalled:
            status = 200
            headers: dict = {}

            def __enter__(self) -> "Stalled":
                return self

            def __exit__(self, *_: object) -> None:
                pass

            def read(self, _size: int) -> bytes:
                waiting.set()
                woke.wait(timeout=5)

                return b""

        def stalled(url: str, headers: dict[str, str] | None = None) -> object:
            return Stalled()

        def wake(response: object) -> None:
            woke.set()

        with mock.patch.object(net, "http_get", side_effect=stalled), mock.patch.object(net, "abort", side_effect=wake):
            worker = threading.Thread(target=self.run_worker_once, daemon=True)
            worker.start()
            self.assertTrue(waiting.wait(timeout=5))
            started = time.monotonic()
            self.store.cancel_all()
            self.assertFalse(self.store.busy())
            worker.join(timeout=5)

        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(worker.is_alive())
        self.assertIn("stopped while downloading", self.log_text())

    def test_overall_progress_counts_running_and_finished_bytes(self) -> None:
        self.queue_two()
        self.store.jobs["a"].phase = "downloading"
        self.store.jobs["a"].done = 100
        self.assertEqual(self.store.batch_progress().fraction, 0.25)
        del self.store.jobs["a"]
        self.store._finish_batch_item(size=self.store.items[0].size)
        self.store.jobs["b"].phase = "downloading"
        self.store.jobs["b"].done = 150
        progress = self.store.batch_progress()
        self.assertEqual((progress.fraction, progress.finished, progress.count), (0.625, 1, 2))

    def test_overall_progress_does_not_count_a_failed_mod_twice(self) -> None:
        self.queue_two()
        self.store.jobs["a"].phase = "error"
        self.store.jobs["a"].done = 60
        self.store._finish_batch_item(size=self.store.items[0].size)
        self.assertEqual(self.store.batch_progress().fraction, 0.25)

    def test_overall_progress_without_sizes_counts_mods(self) -> None:
        self.queue_two(sizes=(0, 0))
        self.store._finish_batch_item(size=self.store.items[0].size)
        self.assertEqual(self.store.batch_progress().fraction, 0.5)

    def test_new_batch_starts_only_when_the_app_is_idle(self) -> None:
        self.queue_two()
        self.store.enqueue(ids=["a"])
        self.assertEqual(self.store.batch.count, 2)
        self.store.jobs.clear()
        self.store.enqueue(ids=["a"])
        self.assertEqual((self.store.batch.count, self.store.batch.total), (1, 100))

    def test_batch_counts_how_each_download_ended(self) -> None:
        self.zip_file(relative="Game.zip", members={f"{TITLE}/romfs/a.bin": b"1"})

        with mock.patch.object(self.store, "_download", return_value=Fetched(wire=self.src / "Game.zip")):
            self.run_worker(item=mod(name="Game", sha256=""))

        self.assertEqual(self.store.batch_progress().saved, 1)

        with mock.patch.object(self.store, "_download", side_effect=OSError("offline")):
            self.run_worker(item=mod(id="two", name="Two", sha256=""))

        self.store.items = [mod(id="three", name="Three", sha256="")]
        self.store.enqueue(ids=["three"])
        self.store.cancel(entry_id="three")
        progress = self.store.batch_progress()
        self.assertEqual((progress.failed, progress.cancelled), (0, 1))

    def test_downloads_run_smallest_first_wherever_they_came_from(self) -> None:
        sizes = {"big": 900, "tiny": 5, "mid": 50, "none": 0}
        self.store.items = [mod(id=name, name=name, size=size) for name, size in sizes.items()]
        self.store.enqueue(ids=["big", "mid"])
        self.store.enqueue(ids=["tiny"])
        self.store.enqueue(ids=["none"])
        order = [self.store.queue.get()[2].id for _ in sizes]
        self.assertEqual(order, ["none", "tiny", "mid", "big"])

    def test_equal_sizes_keep_their_order(self) -> None:
        self.store.items = [mod(id=name, name=name, size=7) for name in ("b", "a")]
        self.store.enqueue(ids=["b", "a"])
        self.assertEqual([self.store.queue.get()[2].id for _ in "ab"], ["b", "a"])
