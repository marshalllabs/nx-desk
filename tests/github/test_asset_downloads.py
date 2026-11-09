import hashlib
import os
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List
from unittest import mock

from nx_desk import uploader, vault
from nx_desk.schemas.common import Progress
from nx_desk.schemas.github import Asset
from nx_desk.utils.callbacks import quiet
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

        def watched(
            store: vault.Vault,
            group: List[str],
            repo: str,
            tag: str,
            assets: Dict[str, Asset],
            root: Path,
            work: Path,
            owner: str,
            moved: Progress = quiet,
        ) -> str:
            seen.append(len(store.upload_snapshot().folders))

            return real(
                self=store,
                group=group,
                repo=repo,
                tag=tag,
                assets=assets,
                root=root,
                work=work,
                owner=owner,
                moved=moved,
            )

        with mock.patch.object(target=vault.Vault, attribute="_download_one", new=watched):
            self.store.download_assets()

        self.assertEqual(first=seen, second=[0, 1])

    def test_download_target_follows_the_release(self) -> None:
        target = vault.Vault._download_target
        self.assertEqual(first=target(root=self.src, tag="reviewed"), second=self.src / "[reviewed]")
        self.assertEqual(first=target(root=self.src / "reviewed", tag="reviewed"), second=self.src / "reviewed")
        self.assertEqual(first=target(root=self.src / "[reviewed]", tag="reviewed"), second=self.src / "[reviewed]")
        (self.src / "my-catalog").mkdir()
        self.assertEqual(first=target(root=self.src, tag="my-catalog"), second=self.src / "my-catalog")

    def test_download_restores_a_folder_with_its_backup(self) -> None:
        self.reupload_then_remove()
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        landed = self.src / "[reviewed]" / "Stardew Valley - [VI] - [1.0]"
        self.assertEqual(first=(landed / "backup" / "old.zip").read_bytes(), second=b"old")
        self.assertEqual(first=self.store.upload_job.fresh_folders, second=["Stardew Valley - [VI] - [1.0]"])

    def test_download_joins_split_parts(self) -> None:
        self.mod(name="Hades - [VI] - [1.0]", data=os.urandom(5000))
        data = (self.src / "Hades - [VI] - [1.0]" / "Hades - [VI] - [1.0].zip").read_bytes()

        with mock.patch.object(target=uploader.archive, attribute="PART_SIZE", new=2000):
            self.store.scan_upload()
            self.store.upload_folders(names=["Hades - [VI] - [1.0]"])

        shutil.rmtree(path=self.src / "Hades - [VI] - [1.0]")
        self.store.download_assets()
        landed = self.src / "[reviewed]" / "Hades - [VI] - [1.0]" / "Hades - [VI] - [1.0].zip"
        self.assertEqual(first=landed.read_bytes(), second=data)

    def test_download_rejects_a_changed_file(self) -> None:
        self.reupload_then_remove()
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = b"tampered"
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        self.assertTrue(expr=self.store.upload_job.failed)
        self.assertFalse(expr=(self.src / "Stardew Valley - [VI] - [1.0]").exists())

    def test_download_refuses_a_zip_that_is_not_one_folder(self) -> None:
        target = self.base / "x.zip"

        with zipfile.ZipFile(file=target, mode="w") as output:
            output.writestr(zinfo_or_arcname="a/1", data="1")
            output.writestr(zinfo_or_arcname="b/2", data="2")

        self.hub.add(name="x.zip", digest=f"sha256:{hashlib.sha256(string=target.read_bytes()).hexdigest()}")
        self.hub.assets["x.zip"].size = target.stat().st_size
        self.hub.blobs["x.zip"] = target.read_bytes()
        self.store.download_assets(names=["x.zip"])
        self.assertIn(member="one top folder", container=self.store.upload_job.message)

    def test_download_beside_a_folder_of_the_same_name(self) -> None:
        self.reupload_then_remove()
        home = self.src / "[reviewed]"
        (home / "Stardew Valley - [VI] - [1.0]").mkdir(parents=True)
        (home / "Stardew Valley - [VI] - [1.0]" / "mine.zip").write_bytes(data=b"mine")
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        self.assertEqual(first=(home / "Stardew Valley - [VI] - [1.0]" / "mine.zip").read_bytes(), second=b"mine")
        self.assertTrue(expr=(home / "Stardew Valley - [VI] - [1.0] (2)" / "backup" / "old.zip").exists())
