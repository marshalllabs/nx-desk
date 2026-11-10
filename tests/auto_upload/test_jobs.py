import http.client
import threading
from pathlib import Path
from typing import Optional
from unittest import mock

from nx_desk import uploader, vault, zips
from nx_desk.schemas.common import Progress, Report
from nx_desk.schemas.github import FolderRef
from nx_desk.utils.callbacks import quiet
from tests.auto_upload.case import AutoUploadCase


class JobTests(AutoUploadCase):
    def test_a_job_stays_open_until_upload_and_delete_are_done(self) -> None:
        self.store.set_auto_delete(enabled=True)
        release, reached = threading.Event(), threading.Event()
        real = vault.Vault._upload_one

        def held(
            store: vault.Vault,
            folder: FolderRef,
            repo: str,
            tag: str,
            stem: str,
            work: Path,
            report: Optional[Report] = None,
            moved: Progress = quiet,
            zipped: Progress = quiet,
        ) -> None:
            reached.set()
            release.wait(timeout=5)

            return real(
                self=store,
                folder=folder,
                repo=repo,
                tag=tag,
                stem=stem,
                work=work,
                report=report,
                moved=moved,
                zipped=zipped,
            )

        with mock.patch.object(target=vault.Vault, attribute="_upload_one", new=held):
            self.run_until_saved(item=self.item())
            self.assertTrue(expr=reached.wait(timeout=5))
            self.assertEqual(first=self.store.jobs["game"].phase, second="zipping")
            self.assertTrue(expr=self.store.busy())
            self.assertEqual(first=self.store.batch_progress().saved, second=0)
            release.set()
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertFalse(expr=self.store.busy())
        self.assertEqual(first=(progress.saved, progress.uploaded, progress.deleted), second=(1, 1, 1))

    def test_a_failed_upload_is_counted_and_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)

        with mock.patch.object(
            target=vault.Vault,
            attribute="_upload_one",
            side_effect=uploader.command.GitHubError("boom"),
        ):
            self.run_until_saved(item=self.item())
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertEqual(first=(progress.saved, progress.uploaded, progress.upload_failed), second=(1, 0, 1))
        self.assertTrue(expr=(self.store.root / "Game - [VI] - [1.0]").is_dir())

    def test_stopping_during_upload_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)
        reached = threading.Event()

        def stopped(store: vault.Vault, *args: object, **kwargs: object) -> None:
            reached.set()
            uploader.command.running.cancel.wait(5)
            uploader.command.stop_point()

        with mock.patch.object(target=vault.Vault, attribute="_upload_one", new=stopped):
            self.run_until_saved(item=self.item())
            self.assertTrue(expr=reached.wait(timeout=5))
            self.store.cancel_all()
            self.assertFalse(expr=self.store.busy())
            self.wait_for_uploads()

        progress = self.store.batch_progress()
        self.assertEqual(first=(progress.cancelled, progress.uploaded), second=(1, 0))
        self.assertTrue(expr=(self.store.root / "Game - [VI] - [1.0]").is_dir())
        self.assertNotIn(member="state.json", container=self.hub.assets)

    def test_stop_prevents_an_api_call(self) -> None:
        cancel = threading.Event()
        cancel.set()

        with (
            uploader.command.stoppable(cancel=cancel),
            mock.patch.object(target=http.client, attribute="HTTPSConnection") as connection,
            self.assertRaises(expected_exception=zips.Cancelled),
            uploader.api.response(url="https://api.github.com/user"),
        ):
            pass

        connection.return_value.request.assert_not_called()
