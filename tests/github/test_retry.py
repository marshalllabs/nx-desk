from pathlib import Path
from typing import List
from unittest import mock

from nx_desk.schemas.common import Progress
from tests.github.case import GitHubCase

HADES = "Hades - [VI] - [1.0]"
STARDEW = "Stardew Valley - [VI] - [1.0]"


class RetryTests(GitHubCase):
    def fail_hades_upload(self) -> None:
        real = self.hub.add

        def add(name: str, digest: str) -> None:
            real(name=name, digest="sha256:wrong" if "Hades" in name else digest)

        self.store.scan_upload()

        with mock.patch.object(target=self.hub, attribute="add", new=add):
            self.store.upload_folders(names=[HADES, STARDEW])

    def test_a_failed_upload_is_kept_for_retry(self) -> None:
        self.fail_hades_upload()
        job = self.store.upload_job
        self.assertEqual(first=(job.retry_kind, job.retry_names, job.retry_tag), second=("upload", [HADES], "reviewed"))

    def test_retry_uploads_only_what_failed(self) -> None:
        self.fail_hades_upload()
        sent: List[str] = []
        real = self.hub.post

        def post(repo: str, release: int, path: Path, token: str, moved: Progress) -> None:
            sent.append(str(path))
            real(repo=repo, release=release, path=path, token=token, moved=moved)

        with mock.patch(target="nx_desk.uploader.upload.post_asset", new=post):
            self.store.retry_failed()

        self.assertEqual(first=len(sent), second=1)
        self.assertIn(member="Hades", container=sent[0])
        self.assertEqual(first=self.statuses()[HADES], second="done")
        self.assertEqual(first=self.store.upload_job.retry_names, second=[])

    def test_retry_of_chosen_failures_leaves_the_rest(self) -> None:
        self.store.scan_upload()
        real = self.hub.add

        with mock.patch.object(
            target=self.hub,
            attribute="add",
            new=lambda name, digest: real(name=name, digest="sha256:wrong"),
        ):
            self.store.upload_folders(names=[HADES, STARDEW])

        self.assertEqual(first=sorted(self.store.upload_job.retry_names), second=[HADES, STARDEW])
        self.store.retry_failed(names=[HADES, "not failed"])
        self.assertEqual(first=self.statuses()[HADES], second="done")
        self.assertEqual(first=self.statuses()[STARDEW], second="error")
        self.assertEqual(first=self.store.upload_job.retry_names, second=[STARDEW])

    def test_retry_waits_for_the_same_release(self) -> None:
        self.fail_hades_upload()
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="other")
        self.store.retry_failed()
        self.assertEqual(first=self.statuses()[HADES], second="error")

    def test_a_failed_download_is_kept_for_retry(self) -> None:
        self.reupload_then_remove()
        good = self.hub.blobs["Stardew-Valley-VI-1-0.zip"]
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = b"tampered"
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        job = self.store.upload_job
        self.assertEqual(first=(job.retry_kind, job.retry_names), second=("download", ["Stardew-Valley-VI-1-0.zip"]))
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = good
        self.store.retry_failed()
        self.assertFalse(expr=self.store.upload_job.failed)
        self.assertTrue(expr=(self.src / "[reviewed]" / STARDEW).is_dir())
