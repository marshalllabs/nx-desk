from unittest import mock

from nx_desk import uploader
from nx_desk.schemas.github import Asset
from tests.github.case import GitHubCase


class AssetListTests(GitHubCase):
    def test_upload_refreshes_the_asset_list(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertEqual([asset.name for asset in self.store.upload_job.assets], ["Hades-VI-1-0.zip"])

    def test_leftover_files_are_hidden_from_the_asset_list(self) -> None:
        self.hub.add(name="uploading-Hades-VI-1-0.zip", digest="sha256:x")
        self.store.load_assets()
        self.assertEqual(self.store.upload_job.assets, [])

    def test_deletes_only_the_chosen_files(self) -> None:
        self.hub.add(name="Hades-VI-1-0.zip", digest="sha256:x")
        self.hub.add(name="Core-VI-1-0.zip", digest="sha256:y")
        self.store.delete_release_assets(names=["Hades-VI-1-0.zip"])
        self.assertEqual(list(self.hub.assets), ["Core-VI-1-0.zip"])
        self.assertEqual([asset.name for asset in self.store.upload_job.assets], ["Core-VI-1-0.zip"])

    def test_choosing_one_part_chooses_the_whole_folder(self) -> None:
        names = ["Big.zip.001", "Big.zip.002", "Big.zip.003", "Bigger.zip", "Other.zip"]
        self.assertEqual(uploader.parts.with_sibling_parts(names=["Big.zip.002"], all_names=names), names[:3])
        self.assertEqual(uploader.parts.with_sibling_parts(names=["Bigger.zip"], all_names=names), ["Bigger.zip"])

    def test_deleted_folder_can_be_uploaded_again(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.store.delete_release_assets(names=["Hades-VI-1-0.zip"])
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        self.assertEqual(list(self.hub.assets), ["Hades-VI-1-0.zip"])
        self.assertEqual(self.statuses()["Hades - [VI] - [1.0]"], "done")

    def test_deleted_files_leave_the_list_one_by_one(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]", "Stardew Valley - [VI] - [1.0]"])
        seen = []
        real = uploader.releases.delete_asset

        def watched(repo: str, asset: Asset) -> None:
            seen.append(len(self.store.upload_snapshot().assets))
            real(repo=repo, asset=asset)

        with mock.patch.object(uploader.releases, "delete_asset", watched):
            self.store.delete_release_assets(names=sorted(self.hub.assets))

        self.assertEqual(seen, [2, 1])
        self.assertEqual({folder.status for folder in self.store.upload_snapshot().folders}, {""})
