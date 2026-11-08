import sys
import threading
import time
from typing import Any
from unittest import mock

from nx_desk import uploader, vault, zips
from tests.auto_upload.case import AutoUploadCase


class JobTests(AutoUploadCase):
    def test_a_job_stays_open_until_upload_and_delete_are_done(self) -> None:
        self.store.set_auto_delete(enabled=True)
        release, reached = threading.Event(), threading.Event()
        real = vault.Vault._upload_one

        def held(store: vault.Vault, *args: Any, **kwargs: Any) -> None:
            reached.set()
            release.wait(timeout=5)

            return real(store, *args, **kwargs)

        with mock.patch.object(vault.Vault, "_upload_one", held):
            self.run_until_saved(item=self.item())
            self.assertTrue(reached.wait(timeout=5))
            self.assertEqual(self.store.jobs["game"].phase, "zipping")
            self.assertTrue(self.store.busy())
            self.assertEqual(self.store.batch_progress().saved, 0)
            release.set()
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertFalse(self.store.busy())
        self.assertEqual((progress.saved, progress.uploaded, progress.deleted), (1, 1, 1))

    def test_a_failed_upload_is_counted_and_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)

        with mock.patch.object(vault.Vault, "_upload_one", side_effect=uploader.command.GhError("boom")):
            self.run_until_saved(item=self.item())
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertEqual((progress.saved, progress.uploaded, progress.upload_failed), (1, 0, 1))
        self.assertTrue((self.store.root / "Game - [VI] - [1.0]").is_dir())

    def test_stopping_during_upload_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)
        reached = threading.Event()

        def stopped(store: vault.Vault, *args: object, **kwargs: object) -> None:
            reached.set()
            uploader.command.running.cancel.wait(5)
            uploader.command.stop_point()

        with mock.patch.object(vault.Vault, "_upload_one", stopped):
            self.run_until_saved(item=self.item())
            self.assertTrue(reached.wait(timeout=5))
            self.store.cancel_all()
            self.assertFalse(self.store.busy())
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertEqual((progress.cancelled, progress.uploaded), (1, 0))
        self.assertTrue((self.store.root / "Game - [VI] - [1.0]").is_dir())
        self.assertNotIn("state.json", self.hub.assets)

    def test_a_long_gh_call_is_killed_by_stop(self) -> None:
        cancel = threading.Event()
        threading.Timer(interval=0.3, function=cancel.set).start()
        started = time.monotonic()

        with uploader.command.stoppable(cancel=cancel), self.assertRaises(zips.Cancelled):
            uploader.command.run_gh(command=sys.executable, args=("-c", "import time; time.sleep(30)"))

        self.assertLess(time.monotonic() - started, 5)
