from unittest import mock

from tests.github.case import GitHubCase

HADES = "Hades - [VI] - [1.0]"
STARDEW = "Stardew Valley - [VI] - [1.0]"


class RetryTests(GitHubCase):
    def fail_hades_upload(self) -> None:
        real = self.hub.add

        def add(name: str, digest: str) -> None:
            real(name, "sha256:wrong" if "Hades" in name else digest)

        self.store.scan_upload()

        with mock.patch.object(self.hub, "add", add):
            self.store.upload_folders(names=[HADES, STARDEW])

    def test_a_failed_upload_is_kept_for_retry(self) -> None:
        self.fail_hades_upload()
        job = self.store.upload_job
        self.assertEqual((job.retry_kind, job.retry_names, job.retry_tag), ("upload", [HADES], "reviewed"))

    def test_retry_uploads_only_what_failed(self) -> None:
        self.fail_hades_upload()
        sent: list[str] = []
        real = self.hub.post

        def post(**fields: object) -> None:
            sent.append(str(fields["path"]))
            real(**fields)  # type: ignore[arg-type]

        with mock.patch("nx_desk.uploader.upload.post_asset", post):
            self.store.retry_failed()

        self.assertEqual(len(sent), 1)
        self.assertIn("Hades", sent[0])
        self.assertEqual(self.statuses()[HADES], "done")
        self.assertEqual(self.store.upload_job.retry_names, [])

    def test_retry_of_chosen_failures_leaves_the_rest(self) -> None:
        self.store.scan_upload()
        real = self.hub.add

        with mock.patch.object(self.hub, "add", lambda name, digest: real(name, "sha256:wrong")):
            self.store.upload_folders(names=[HADES, STARDEW])

        self.assertEqual(sorted(self.store.upload_job.retry_names), [HADES, STARDEW])
        self.store.retry_failed(names=[HADES, "not failed"])
        self.assertEqual(self.statuses()[HADES], "done")
        self.assertEqual(self.statuses()[STARDEW], "error")
        self.assertEqual(self.store.upload_job.retry_names, [STARDEW])

    def test_retry_waits_for_the_same_release(self) -> None:
        self.fail_hades_upload()
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="other")
        self.store.retry_failed()
        self.assertEqual(self.statuses()[HADES], "error")

    def test_a_failed_download_is_kept_for_retry(self) -> None:
        self.reupload_then_remove()
        good = self.hub.blobs["Stardew-Valley-VI-1-0.zip"]
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = b"tampered"
        self.store.download_assets(names=["Stardew-Valley-VI-1-0.zip"])
        job = self.store.upload_job
        self.assertEqual((job.retry_kind, job.retry_names), ("download", ["Stardew-Valley-VI-1-0.zip"]))
        self.hub.blobs["Stardew-Valley-VI-1-0.zip"] = good
        self.store.retry_failed()
        self.assertFalse(self.store.upload_job.failed)
        self.assertTrue((self.src / "[reviewed]" / STARDEW).is_dir())
