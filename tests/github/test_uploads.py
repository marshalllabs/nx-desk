import os
import zipfile
from unittest import mock

from nx_desk import uploader
from tests.github.case import GitHubCase
from tests.helpers import asset


class UploadTests(GitHubCase):
    def test_upload_lists_each_new_file_as_it_lands(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"])
        job = self.store.upload_job
        self.assertEqual(sorted(job.fresh_assets), ["Hades-VI-1-0.zip", "Stardew-Valley-VI-1-0.zip"])
        self.assertEqual(len(job.assets), 2)

    def test_every_upload_replaces_the_old_file(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        first = self.hub.assets["Hades-VI-1-0.zip"]["id"]
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertEqual(list(self.hub.assets), ["Hades-VI-1-0.zip"])
        self.assertNotEqual(self.hub.assets["Hades-VI-1-0.zip"]["id"], first)

    def test_a_new_version_is_a_separate_file(self) -> None:
        self.mod(name="Stardew Valley - [VI] - [1.1]", data=b"newer")
        self.store.scan_upload()
        self.store.upload_folders(names=["Stardew Valley - [VI] - [1.0]", "Stardew Valley - [VI] - [1.1]"])
        self.assertEqual(sorted(self.hub.assets), ["Stardew-Valley-VI-1-0.zip", "Stardew-Valley-VI-1-1.zip"])

    def test_names_keep_apart_from_similar_folders(self) -> None:
        assets = {
            name: asset(name=name) for name in ("Game-VI-1-0.zip", "Game-VI-Characters-1-0.zip", "Game-II-VI.zip")
        }
        self.assertEqual(list(uploader.parts.owned_assets(stem="Game-VI-1-0", assets=assets)), ["Game-VI-1-0.zip"])

    def test_asset_name_comes_from_the_folder(self) -> None:
        folder = self.mod(name="Castlevania Belmonts Curse - [VI] - [1.1.0-v65536]")
        self.assertEqual(uploader.archive.asset_base(folder=folder), "Castlevania-Belmonts-Curse-VI-1-1-0-v65536")

    def test_uploads_only_the_chosen_folders(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Stardew Valley - [VI] - [1.0]"])
        self.assertEqual(list(self.hub.assets), ["Stardew-Valley-VI-1-0.zip"])
        self.assertEqual(self.statuses(), {"Hades - [VI] - [1.0]": "", "Stardew Valley - [VI] - [1.0]": "done"})

    def test_uploads_the_smallest_folder_first(self) -> None:
        self.mod(name="Big - [VI] - [1.0]", data=b"x" * 9000)
        self.store.scan_upload()
        self.store.upload_folders(names=["Big - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]", "Hades - [VI] - [1.0]"])
        order = sorted(self.hub.assets.values(), key=lambda asset: asset["id"])
        self.assertEqual(
            [asset["name"] for asset in order],
            ["Hades-VI-1-0.zip", "Stardew-Valley-VI-1-0.zip", "Big-VI-1-0.zip"],
        )

    def test_changed_folder_replaces_its_old_file(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        before = self.hub.assets["Hades-VI-1-0.zip"]["digest"]
        self.mod(name="Hades - [VI] - [1.0]", data=b"new")
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertEqual(list(self.hub.assets), ["Hades-VI-1-0.zip"])
        self.assertNotEqual(self.hub.assets["Hades-VI-1-0.zip"]["digest"], before)

    def test_mismatch_keeps_the_old_file(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.mod(name="Hades - [VI] - [1.0]", data=b"new")
        real = self.hub.add

        with mock.patch.object(self.hub, "add", lambda name, digest: real(name, "sha256:wrong")):
            self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        self.assertEqual(self.statuses()["Hades - [VI] - [1.0]"], "error")
        self.assertIn("Hades-VI-1-0.zip", self.hub.assets)

    def test_large_zip_is_split_and_rejoins(self) -> None:
        self.mod(name="Hades - [VI] - [1.0]", data=os.urandom(5000))

        with mock.patch.object(uploader.archive, "PART_SIZE", 2000):
            self.store.scan_upload()
            self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        self.assertEqual(
            sorted(self.hub.assets),
            ["Hades-VI-1-0.zip.001", "Hades-VI-1-0.zip.002", "Hades-VI-1-0.zip.003"],
        )

    def test_keeps_files_that_are_only_on_the_release(self) -> None:
        self.hub.add(name="Other-VI.zip", digest="sha256:x")
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertIn("Other-VI.zip", self.hub.assets)

    def test_clears_leftovers_of_a_stopped_upload(self) -> None:
        self.hub.add(name="uploading-Hades-VI-1-0.zip", digest="sha256:x")
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertEqual(list(self.hub.assets), ["Hades-VI-1-0.zip"])

    def test_zip_keeps_the_folder_and_its_backup(self) -> None:
        target = self.base / "out.zip"
        uploader.archive.build_zip(folder=self.src / "Stardew Valley - [VI] - [1.0]", target=target)

        with zipfile.ZipFile(file=target) as archive:
            self.assertIn("Stardew Valley - [VI] - [1.0]/backup/old.zip", archive.namelist())
