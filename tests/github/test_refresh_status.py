from tests.github.case import GitHubCase


class RefreshUploadStatusTests(GitHubCase):
    def test_scan_resets_finished_status_and_progress(self) -> None:
        self.store.scan_upload()
        folder = self.store.upload_job.folders[0]
        folder.status = "error"
        folder.message = "old upload error"
        folder.progress = "Uploading 50%"
        self.store.scan_upload()

        for item in self.store.upload_job.folders:
            self.assertEqual(first=(item.status, item.message, item.progress), second=("", "", ""))

    def test_scan_preserves_progress_during_upload(self) -> None:
        self.store.scan_upload()
        folder = self.store.upload_job.folders[0]
        folder.status = "working"
        folder.progress = "Uploading 50%"
        self.store.upload_job.phase = "uploading"
        self.store._scan_source()
        item = next(item for item in self.store.upload_job.folders if item.name == folder.name)
        self.assertEqual(first=(item.status, item.progress), second=("working", "Uploading 50%"))
