import shutil
from collections.abc import Collection
from pathlib import Path

from .. import uploader
from ..names import GAME_FOLDER, folder_zip_names
from ..schemas.github import Folder, FolderRef, TreeNode
from ..utils.files import tree_size
from ..utils.text import plural
from .github_job import GitHubJob


class UploadSource(GitHubJob):
    # A game folder (new format) is one upload unit; a plain folder is a container that holds
    # them. Branches with no game folder under them are dropped from the tree.
    def _scan_tree(self, path: Path, units: list[Folder]) -> TreeNode | None:
        if GAME_FOLDER.match(string=path.name):
            # A mod folder is a leaf. It is a unit only when it holds a zip of the same name;
            # otherwise it is shown as invalid and left out of uploads.
            size = tree_size(path=path)

            if any((path / name).is_file() for name in folder_zip_names(folder=path.name)):
                units.append(
                    Folder(
                        name=path.name,
                        path=path,
                        size=size,
                        status="",
                        message="",
                        progress="",
                        asset=f"{uploader.archive.asset_stem(name=path.name)}.zip",
                    ),
                )

                return TreeNode(name=path.name, size=size, children=[], unit=path.name, invalid=False)

            return TreeNode(name=path.name, size=size, children=[], unit=None, invalid=True)

        children = []

        for child in sorted(path.iterdir(), key=lambda p: p.name.casefold()):
            if child.is_dir() and not child.is_symlink():
                node = self._scan_tree(path=child, units=units)

                if node:
                    children.append(node)

        if not children:
            return None

        size = sum(node.size for node in children)

        return TreeNode(name=path.name, size=size, children=children, unit=None, invalid=False)

    def _scan_source(self) -> str:
        root = Path(self.upload_source).expanduser().resolve()

        if not self.upload_source or not root.is_dir():
            raise ValueError("Choose a source folder")

        units: list[Folder] = []
        nodes: list[TreeNode] = []

        for child in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if child.is_dir() and not child.is_symlink():
                node = self._scan_tree(path=child, units=units)

                if node:
                    nodes.append(node)

        with self.lock:
            # Only an active upload keeps progress; a refresh recomputes finished row states.
            known = {
                folder.name: folder
                for folder in self.upload_job.folders
                if self.upload_job.phase == "uploading" or folder.status == "working"
            }

            for unit in units:
                old = known.get(unit.name, unit)
                unit.status = old.status
                unit.message = old.message
                unit.progress = old.progress

            tree = self.upload_job.tree + 1
            self.upload_job.folders = units
            self.upload_job.tree_nodes = nodes
            self.upload_job.tree = tree

        return ""

    def _mark_folder(self, name: str, **fields: object) -> None:
        with self.lock:
            for folder in self.upload_job.folders:
                if folder.name == name:
                    for key, value in fields.items():
                        setattr(folder, key, value)

    # The source panel follows mods saved or removed from the Catalog tab too.
    def _source_changed(self, path: Path) -> None:
        source = Path(self.upload_source).expanduser().resolve() if self.upload_source else None

        if source and source.is_dir() and (source == path or source in path.parents):
            try:
                self._scan_source()
            except (OSError, ValueError) as error:
                self._log_github(text=f"could not scan the source folder: {error}", level="warn")

    def scan_upload(self) -> None:
        self._run_upload_step(phase="loading", step=self._scan_source)

    # Only a mod folder found under the source is ever removed, never the source or a folder above it.
    def _delete_local(self, folder: FolderRef) -> bool:
        root = Path(self.upload_source).expanduser().resolve()
        path = folder.path.resolve()

        if not self.upload_source or root not in path.parents:
            self._log_folder(
                folder_name=folder.name,
                text="not deleted: it is not under the source folder",
                level="error",
            )

            return False

        try:
            shutil.rmtree(path=path)
        except OSError as error:
            self._log_folder(folder_name=folder.name, text=f"could not delete the local copy: {error}", level="error")

            return False

        self._log_folder(folder_name=folder.name, text=f"deleted the local copy {folder.name}")

        return True

    def delete_source_folders(self, names: Collection[str]) -> None:
        def step() -> str:
            with self.lock:
                chosen = [folder for folder in self.upload_job.folders if folder.name in names]

            deleted = sum(self._delete_local(folder=folder) for folder in chosen)
            self._scan_source()
            text = f"Deleted {plural(count=deleted, word='folder')} from the source folder."

            if deleted < len(chosen):
                raise OSError(f"{text} {len(chosen) - deleted} could not be deleted; see the log.")

            return text

        self._run_upload_step(phase="loading", step=step)
