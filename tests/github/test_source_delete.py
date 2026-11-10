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
        self.assertIn(member="Hades-VI-1-0.zip", container=self.hub.assets)
        self.assertFalse(expr=(self.src / HADES).exists())
        self.assertTrue(expr=(self.src / STARDEW).exists())
        self.assertEqual(first=[folder.name for folder in self.store.upload_job.folders], second=[STARDEW])
        self.assertIn(member="Deleted 1 local copy.", container=self.store.upload_job.message)

    def test_a_failed_upload_keeps_the_folder(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.store.scan_upload()
        real = self.hub.add

        with mock.patch.object(
            target=self.hub,
            attribute="add",
            new=lambda name, digest: real(name=name, digest="sha256:wrong"),
        ):
            self.store.upload_folders(names=[HADES])

        self.assertTrue(expr=(self.src / HADES).exists())

    def test_a_failed_state_write_keeps_the_folder(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.store.scan_upload()
        broken = uploader.command.GitHubError("HTTP 502")

        with mock.patch.object(target=vault.Vault, attribute="_record_in_state", side_effect=broken):
            self.store.upload_folders(names=[HADES])

        self.assertIn(member="Hades-VI-1-0.zip", container=self.hub.assets)
        self.assertTrue(expr=(self.src / HADES).exists())

    def test_off_keeps_every_folder(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=[HADES])
        self.assertTrue(expr=(self.src / HADES).exists())

    def test_the_choice_is_saved(self) -> None:
        self.store.set_upload_delete(enabled=True)
        self.assertTrue(expr=vault.Vault(base=self.base / "data").upload_delete)


class DeleteSourceFolderTests(GitHubCase):
    def test_deletes_only_the_chosen_folders(self) -> None:
        self.store.scan_upload()
        self.store.delete_source_folders(names=[HADES])
        self.assertFalse(expr=(self.src / HADES).exists())
        self.assertTrue(expr=(self.src / STARDEW).exists())
        self.assertEqual(first=[folder.name for folder in self.store.upload_job.folders], second=[STARDEW])
        self.assertFalse(expr=self.store.upload_job.failed)

    def test_never_deletes_outside_the_source(self) -> None:
        outside = self.base / "elsewhere" / HADES
        outside.mkdir(parents=True)
        self.assertFalse(expr=self.store._delete_local(folder=FolderRef(name=HADES, path=outside, size=0)))
        self.assertTrue(expr=outside.exists())
        self.assertFalse(expr=self.store._delete_local(folder=FolderRef(name="src", path=Path(self.src), size=0)))
        self.assertTrue(expr=self.src.exists())
