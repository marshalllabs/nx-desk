import hashlib
import os
import shutil
import zipfile
from typing import Any
from unittest import mock

from nx_desk import uploader, vault
from tests.github.case import GitHubCase


class AssetDownloadTests(GitHubCase):
    def test_download_shows_each_folder_as_it_arrives(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"])

        for name in ("Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"):
            shutil.rmtree(path=self.src / name)

        self.store.scan_upload()
        seen = []
        real = vault.Vault._download_one

        def watched(store: vault.Vault, *args: Any, **kwargs: Any) -> str:
            seen.append(len(store.upload_snapshot().folders))

            return real(store, *args, **kwargs)

        with mock.patch.object(vault.Vault, "_download_one", watched):
            self.store.download_assets()

        self.assertEqual(seen, [0, 1])

    def test_download_target_follows_the_release(self) -> None:
        target = vault.Vault._download_target
        self.assertEqual(target(root=self.src, tag="reviewed"), self.src / "[reviewed]")
        self.assertEqual(target(root=self.src / "reviewed", tag="reviewed"), self.src / "reviewed")
        self.assertEqual(target(root=self.src / "[reviewed]", tag="reviewed"), self.src / "[reviewed]")
        (self.src / "my-catalog").mkdir()
        self.assertEqual(target(root=self.src, tag="my-catalog"), self.src / "my-catalog")

    def test_download_restores_a_folder_with_its_backup(self) -> None:
        self.reupload_then_remove()
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        landed = self.src / "[reviewed]" / "Stardew Valley - [VI] - [1.0]"
        self.assertEqual((landed / "backup" / "old.zip").read_bytes(), b"old")
        self.assertEqual(self.store.upload_job.fresh_folders, ["Stardew Valley - [VI] - [1.0]"])

    def test_download_joins_split_parts(self) -> None:
        self.mod(name="Hades - [VI] - [1.0]", data=os.urandom(5000))
        data = (self.src / "Hades - [VI] - [1.0]" / "Hades - [VI] - [1.0].zip").read_bytes()

        with mock.patch.object(uploader.archive, "PART_SIZE", 2000):
            self.store.scan_upload()
            self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        shutil.rmtree(path=self.src / "Hades - [VI] - [1.0]")
        self.store.download_assets()
        landed = self.src / "[reviewed]" / "Hades - [VI] - [1.0]" / "Hades - [VI] - [1.0].zip"
        self.assertEqual(landed.read_bytes(), data)

    def test_download_rejects_a_changed_file(self) -> None:
        self.reupload_then_remove()
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = b"tampered"
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        self.assertTrue(self.store.upload_job.failed)
        self.assertFalse((self.src / "Stardew Valley - [VI] - [1.0]").exists())

    def test_download_refuses_a_zip_that_is_not_one_folder(self) -> None:
        target = self.base / "x.zip"

        with zipfile.ZipFile(file=target, mode="w") as output:
            output.writestr(zinfo_or_arcname="a/1", data="1")
            output.writestr(zinfo_or_arcname="b/2", data="2")

        self.hub.add(name="x.zip", digest=f"sha256:{hashlib.sha256(target.read_bytes()).hexdigest()}")
        self.hub.assets["x.zip"]["size"] = target.stat().st_size
        self.hub.blobs["x.zip"] = target.read_bytes()
        self.store.download_assets(names=["x.zip"])
        self.assertIn("one top folder", self.store.upload_job.message)

    def test_download_beside_a_folder_of_the_same_name(self) -> None:
        self.reupload_then_remove()
        home = self.src / "[reviewed]"
        (home / "Stardew Valley - [VI] - [1.0]").mkdir(parents=True)
        (home / "Stardew Valley - [VI] - [1.0]" / "mine.zip").write_bytes(data=b"mine")
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        self.assertEqual((home / "Stardew Valley - [VI] - [1.0]" / "mine.zip").read_bytes(), b"mine")
        self.assertTrue((home / "Stardew Valley - [VI] - [1.0] (2)" / "backup" / "old.zip").exists())
