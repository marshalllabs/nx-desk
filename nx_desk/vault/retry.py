from collections.abc import Collection

from .asset_downloads import AssetDownloads
from .uploads import Uploads


class Retrying(AssetDownloads, Uploads):
    # Runs the last upload or download again for what failed, or for the chosen ones of those, while
    # the same release is chosen.
    def retry_failed(self, names: Collection[str] | None = None) -> None:
        with self.lock:
            job = self.upload_job
            kind, tag = job.retry_kind, job.retry_tag
            chosen = [name for name in job.retry_names if names is None or name in names]
            # Failures left out of this retry stay listed after it.
            kept = [name for name in job.retry_names if name not in chosen]

        if not chosen or tag != self.upload_tag:
            return

        if kind == "upload":
            self.upload_folders(names=chosen)
        elif kind == "download":
            self.download_assets(names=chosen)

        with self.lock:
            job = self.upload_job

            if (job.retry_kind, job.retry_tag) == (kind, tag):
                job.retry_names = kept + [name for name in job.retry_names if name not in kept]
