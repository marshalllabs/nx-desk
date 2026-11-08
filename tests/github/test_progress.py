import time
from unittest import mock

from nx_desk import uploader, vault
from nx_desk.schemas.github import Transfer
from nx_desk.utils.files import tree_size
from tests.github.case import GitHubCase


class ProgressTests(GitHubCase):
    def test_uploads_report_bytes_for_the_whole_run(self) -> None:
        self.store.scan_upload()
        seen = []
        real = vault.Vault._meter

        def watched(store: vault.Vault, label: str, done: int, total: int) -> None:
            seen.append((label, done, total))
            real(store, label, done, total)

        with mock.patch.object(vault.Vault, "_meter", watched):
            self.store.upload_folders(names=["Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"])

        self.assertEqual(seen[0][0], "Zipping 1/2")
        self.assertIn("Uploading 1/2", [label for label, _, _ in seen])
        self.assertEqual(seen[-1][0], "Uploading 2/2")
        self.assertIsNone(self.store.upload_snapshot().transfer)

    def test_the_meter_works_out_speed_from_samples(self) -> None:
        with mock.patch.object(time, "monotonic", side_effect=[0, 1, 1.1]):
            self.store._meter(label="Up", done=0, total=100)
            self.store._meter(label="Up", done=40, total=100)
            self.store._meter(label="Up", done=41, total=100)

        moving = self.store.upload_snapshot().transfer
        assert moving is not None
        self.assertEqual((moving.done, moving.speed), (40, 40))

    def test_zipping_counts_the_bytes_written(self) -> None:
        folder = self.src / "Hades - [VI] - [1.0]"
        moved: list[int] = []
        uploader.archive.build_zip(folder=folder, target=self.base / "out.zip", moved=moved.append)
        self.assertEqual(moved[-1], tree_size(path=folder))

    def test_a_new_stage_starts_its_own_speed(self) -> None:
        with mock.patch.object(time, "monotonic", side_effect=[0, 1, 1.1]):
            self.store._meter(label="Zipping", done=0, total=100)
            self.store._meter(label="Zipping", done=50, total=100)
            self.store._meter(label="Uploading", done=60, total=100)

        moving = self.store.upload_snapshot().transfer
        assert moving is not None
        self.assertEqual((moving.label, moving.speed), ("Uploading", 0))

    def test_cancel_stops_the_upload_that_is_running(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        before = dict(self.hub.assets["Hades-VI-1-0.zip"])

        def cut_off(*_args: object, **_kwargs: object) -> None:
            self.store.upload_cancel.set()
            uploader.command.stop_point()

        with mock.patch.object(uploader.archive, "build_zip", cut_off):
            self.store.upload_folders(names=["Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"])

        self.assertEqual(self.hub.assets["Hades-VI-1-0.zip"], before)
        self.assertNotIn("Stardew-Valley-VI-1-0.zip", self.hub.assets)
        job = self.store.upload_snapshot()
        self.assertEqual(job.phase, "idle")
        self.assertTrue(job.message.startswith("Cancelled."))

    def test_cancel_stops_the_download_that_is_running(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        def cut_off(*_args: object, **_kwargs: object) -> None:
            self.store.upload_cancel.set()
            uploader.command.stop_point()

        with mock.patch.object(uploader.parts, "download_group", cut_off):
            self.store.download_assets()

        job = self.store.upload_snapshot()
        self.assertEqual(job.phase, "idle")
        self.assertTrue(job.message.startswith("Cancelled."))
        self.assertFalse((self.src / "[reviewed]").exists())

    def test_rows_report_their_own_progress(self) -> None:
        self.store.scan_upload()
        seen: list[str] = []
        real = vault.Vault._mark_folder

        def watched(store: vault.Vault, name: str, **fields: object) -> None:
            seen.append(str(fields.get("progress") or ""))
            real(store, name, **fields)

        with mock.patch.object(vault.Vault, "_mark_folder", watched):
            self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        self.assertEqual(seen[0], "Queued")
        self.assertTrue(any(text.startswith("Zipping") for text in seen))
        self.assertTrue(any(text.startswith("Uploading") for text in seen))

        self.assertEqual({folder.progress for folder in self.store.upload_snapshot().folders}, {""})

    def test_progress_text_shows_the_share_and_speed(self) -> None:
        self.store._set_upload(transfer=Transfer(label="Up", done=1, total=4, speed=2 * 1024**2))
        self.assertEqual(self.store._progress_text(verb="Uploading", done=1, total=4), "Uploading 25% · 2.0 MiB/s")
        self.store._set_upload(transfer=None)
        self.assertEqual(self.store._progress_text(verb="Zipping", done=5, total=4), "Zipping 100%")
