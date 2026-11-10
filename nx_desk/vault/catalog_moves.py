from typing import List, Optional

from .. import uploader
from ..names import art_slug
from ..schemas.catalog import Catalog
from ..schemas.files import FileMove
from ..schemas.github import ReleaseRenames
from ..schemas.state import RELEASE_STATE, ReleaseState
from .github_job import GitHubJob
from .jobs import Jobs
from .release_state import ReleaseStates


# Renaming a catalog also renames its folder, which is the name of its release on GitHub, so the two stay linked.
class CatalogMoves(Jobs, GitHubJob, ReleaseStates):
    # The folder a name gives: its slug, made unique among the other catalogs.
    def _free_folder(self, name: str, skip: Optional[Catalog] = None) -> str:
        taken = {catalog.folder for catalog in self.catalogs if catalog is not skip}
        slug = art_slug(name=name) or "catalog"
        folder, number = slug, 2

        while folder in taken:
            folder, number = f"{slug}-{number}", number + 1

        return folder

    # Everything on disk that carries the folder name: the catalog's own folder, its downloads and its art.
    def _folder_paths(self, old: str, new: str) -> List[FileMove]:
        places = (self.catalogs_dir, self._download_root(), self.base / "covers")
        pairs = [FileMove(source=place / old, target=place / new) for place in places]

        return [pair for pair in pairs if pair.source.exists() or pair.target.exists()]

    # The repositories where a catalog's release may live: the one for automatic uploads and the GitHub tab's.
    def _release_repos(self) -> List[str]:
        repos = [self.auto_repo, self.upload_repo]

        return list(dict.fromkeys(repo for repo in repos if uploader.releases.REPO_NAME.match(string=repo)))

    # Gives the catalog the folder `new`, with its release, files and downloads. Returns what to tell the user.
    # Nothing changes when it cannot be done in full: a release is only renamed when GitHub allows it everywhere it
    # lives, and the folder only follows when that worked, so the catalog and its release stay linked.
    def _rename_folder(self, catalog: Catalog, new: str) -> List[str]:
        old = catalog.folder

        with self.lock:
            if catalog is self.catalog and (self.busy() or self.checking):
                raise ValueError("wait for downloads and the catalog check to finish before renaming this catalog")

            pairs = self._folder_paths(old=old, new=new)

            if any(pair.target.exists() for pair in pairs):
                return [f"The folder kept its name, {new} is already used."]

        try:
            self._login()

        except uploader.command.GitHubError:
            return ["The folder and its release kept their names, since GitHub authentication is unavailable."]

        renames = self._rename_releases(old=old, new=new)
        renamed = renames.repos
        notes = renames.notes

        try:
            self._move_paths(pairs=pairs)

        except OSError as error:
            self._undo_releases(repos=renamed, old=old, new=new)

            raise ValueError(f"could not move the catalog's files: {error}") from error

        self._take_folder(catalog=catalog, old=old, new=new, repos=renamed)

        return notes

    # Renames the release in each repository that has one, or none at all, and removes the old tag it leaves behind.
    # Returns the repositories it changed and what to tell the user.
    def _rename_releases(self, old: str, new: str) -> ReleaseRenames:
        found: List[str] = []

        for repo in self._release_repos():
            try:
                tags = uploader.releases.list_releases(repo=repo)

            except uploader.command.GitHubError as error:
                raise ValueError(f"could not read the releases of {repo}: {error}") from error

            if new in tags:
                raise ValueError(f"{repo} already has a release named {new}")

            if old in tags:
                found.append(repo)

        done: List[str] = []
        notes: List[str] = []

        for repo in found:
            try:
                with self.github_lock:
                    uploader.releases.rename_release(repo=repo, tag=old, new_tag=new)

            except uploader.command.GitHubError as error:
                self._undo_releases(repos=done, old=old, new=new)

                raise ValueError(f"could not rename the release in {repo}: {error}") from error

            done.append(repo)
            self._log_github(text=f"Renamed release {old} to {new} in {repo}")

            if uploader.releases.delete_tag(repo=repo, tag=old):
                notes.append(f"Renamed the release to {new} in {repo} and removed its old tag {old}.")

            else:
                notes.append(f"Renamed the release to {new} in {repo}, but its old tag {old} could not be removed.")
                self._log_github(text=f"Could not remove the old tag {old} in {repo}", level="warn")

        return ReleaseRenames(repos=done, notes=notes)

    # Best effort: a release already renamed goes back, with the tag it made going too, so a failure leaves the
    # catalog and its repositories as they were.
    def _undo_releases(self, repos: List[str], old: str, new: str) -> None:
        for repo in repos:
            try:
                with self.github_lock:
                    uploader.releases.rename_release(repo=repo, tag=new, new_tag=old)

            except uploader.command.GitHubError as error:
                self._log_github(text=f"Could not rename release {new} back to {old} in {repo}: {error}", level="error")

                continue

            uploader.releases.delete_tag(repo=repo, tag=new)

    @staticmethod
    def _move_paths(pairs: List[FileMove]) -> None:
        done: List[FileMove] = []

        try:
            for pair in pairs:
                source, target = pair.source, pair.target

                if source.exists():
                    source.rename(target)
                    done.append(pair)

        except OSError:
            for pair in reversed(done):
                source, target = pair.source, pair.target
                target.rename(source)

            raise

    # The catalog now lives under its new folder: fix what points at the old one.
    def _take_folder(self, catalog: Catalog, old: str, new: str, repos: List[str]) -> None:
        cache = self._release_cache(folder=new)
        state = self._load_model(path=cache, schema=RELEASE_STATE, default=ReleaseState())

        if state.tag == old and cache.exists():
            self._write_json(path=cache, value=state.model_copy(update={"tag": new}))

        with self.lock:
            catalog.folder = new

            if catalog is self.catalog:
                self._use_catalog(catalog=catalog)

            # The GitHub tab shows the releases of its repository, so the one that was renamed changes there too.
            if self.upload_repo in repos:
                self._rename_in_tab(old=old, new=new)

            self._save_registry()

    def _rename_in_tab(self, old: str, new: str) -> None:
        if self.upload_tag == old:
            self.upload_tag = new

        job = self.upload_job
        job.releases = [new if tag == old else tag for tag in job.releases]
        job.latest_release = new if job.latest_release == old else job.latest_release
        job.select_tag = new if job.select_tag == old else job.select_tag
        job.release_list += 1
