from pathlib import Path
from unittest import mock

from nx_desk import uploader, vault
from nx_desk.schemas.github import FolderRef
from tests.github.case import GitHubCase

HADES = "Hades - [VI] - [1.0]"
STARDEW = "Stardew Valley - [VI] - [1.0]"


class DeleteAfterUploadTests(GitHubCase):
    def test_a_folder_goes_once_it_is_on_the_release(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.store.scan_upload()
        self.store.upload_folders(names=[HADES])
        self.assertIn("Hades-VI-1-0.zip", self.hub.assets)
        self.assertFalse((self.src / HADES).exists())
        self.assertTrue((self.src / STARDEW).exists())
        self.assertEqual([folder.name for folder in self.store.upload_job.folders], [STARDEW])
        self.assertIn("Deleted 1 local copy.", self.store.upload_job.message)

    def test_a_failed_upload_keeps_the_folder(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.store.scan_upload()
        real = self.hub.add

        with mock.patch.object(self.hub, "add", lambda name, digest: real(name, "sha256:wrong")):
            self.store.upload_folders(names=[HADES])

        self.assertTrue((self.src / HADES).exists())

    def test_a_failed_state_write_keeps_the_folder(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.store.scan_upload()
        broken = uploader.command.GhError("HTTP 502")

        with mock.patch.object(vault.Vault, "_record_in_state", side_effect=broken):
            self.store.upload_folders(names=[HADES])

        self.assertIn("Hades-VI-1-0.zip", self.hub.assets)
        self.assertTrue((self.src / HADES).exists())

    def test_off_keeps_every_folder(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=[HADES])
        self.assertTrue((self.src / HADES).exists())

    def test_the_choice_is_saved(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.assertTrue(vault.Vault(base=self.base / "data").upload_delete)


class DeleteSourceFolderTests(GitHubCase):
    def test_deletes_only_the_chosen_folders(self) -> None:
        self.store.scan_upload()
        self.store.delete_source_folders(names=[HADES])
        self.assertFalse((self.src / HADES).exists())
        self.assertTrue((self.src / STARDEW).exists())
        self.assertEqual([folder.name for folder in self.store.upload_job.folders], [STARDEW])
        self.assertFalse(self.store.upload_job.failed)

    def test_never_deletes_outside_the_source(self) -> None:
        outside = self.base / "elsewhere" / HADES
        outside.mkdir(parents=True)
        self.assertFalse(self.store._delete_local(folder=FolderRef(name=HADES, path=outside, size=0)))
        self.assertTrue(outside.exists())
        self.assertFalse(self.store._delete_local(folder=FolderRef(name="src", path=Path(self.src), size=0)))
        self.assertTrue(self.src.exists())
