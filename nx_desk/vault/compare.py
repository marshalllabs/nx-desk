from .. import uploader
from .source import UploadSource


class Comparing(UploadSource):
    # Loads a second release of the same repository, shown beside the chosen one.
    def load_compare(self, tag: str) -> None:
        def step() -> str:
            repo = self._upload_repo()
            name = tag.strip()

            if not name:
                raise ValueError("Choose a release to compare with")

            assets = uploader.releases.remote_assets(repo=repo, tag=name)
            rows = [asset for key, asset in assets.items() if self._listed(name=key)]

            with self.lock:
                job = self.upload_job
                job.compare_tag = name
                job.compare_assets = rows
                job.compare_list = job.compare_list + 1

            return f"Comparing with release {name}, which has {uploader.parts.games_text(assets=rows)}."

        self._run_upload_step(phase="loading", step=step)

    def close_compare(self) -> None:
        with self.lock:
            job = self.upload_job
            job.compare_tag = ""
            job.compare_assets = []
            job.compare_list = job.compare_list + 1
