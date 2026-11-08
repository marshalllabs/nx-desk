from collections.abc import Collection

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem

from ... import uploader
from ...names import format_size
from ...utils.text import plural
from ..dialogs import ask_yes_no, confirm, confirm_typed
from ..rows import total_text
from .selection import Selection


class Transfers(Selection):
    # Each chosen source folder with its size and whether the release has it.
    def folder_rows(self, names: Collection[str]) -> tuple[list[tuple[str, str, str]], str]:
        job = self.vault.upload_snapshot()
        folders = {folder.name: folder for folder in job.folders}
        assets = {asset.name: asset for asset in job.assets}
        rows = []

        for name in names:
            folder = folders.get(name)
            size = folder.size if folder else 0
            on_release = folder is not None and bool(
                uploader.parts.owned_assets(stem=folder.asset.removesuffix(".zip"), assets=assets),
            )
            rows.append((name, format_size(value=size) if size else "-", "Replaced" if on_release else "New"))

        total = sum(folders[name].size for name in names if name in folders)

        return rows, total_text(size=total)

    def confirm_upload(self, title: str, names: Collection[str]) -> bool:
        rows, total = self.folder_rows(names=names)
        title = self.upload_text(text=title, names=names)
        text = f"{self.upload_text(text='Upload', names=names)} {plural(count=len(names), word='mod')} to release {self.tag}?"

        if self.vault.upload_delete:
            text += "\n\nEach source folder is deleted once it is on the release."

        return not self.vault.uploading() and confirm(
            title=title,
            question=text,
            columns=("Folder", "Size", "On the release"),
            rows=rows,
            parent=self.app,
            total=total,
        )

    def delete_folders(self) -> None:
        names = sorted(self.selected_folders())
        rows, total = self.folder_rows(names=names)
        rows = [(name, size, "Yes" if state == "Replaced" else "No") for name, size, state in rows]
        text = f"This deletes {plural(count=len(names), word='folder')} from the source folder on disk. It cannot be undone."

        # Folder names are long and full of brackets, so the word to type is "delete".
        if (
            names
            and not self.vault.uploading()
            and confirm_typed(
                title="Delete folders",
                message=text,
                word="delete",
                action="Delete folders",
                parent=self.app,
                table=(("Folder", "Size", "On the release"), rows, total),
            )
        ):
            self.run(self.vault.delete_source_folders, names)

    def upload(self) -> None:
        names = sorted(self.selected_folders())

        if self.confirm_upload(title="Upload", names=names):
            self.run(self.vault.upload_folders, names)

    def upload_all(self) -> None:
        names = sorted(self.unit_of.values())

        if self.confirm_upload(title="Upload all", names=names):
            self.run(self.vault.upload_folders, names)

    def confirm_retry(self, title: str, names: list[str]) -> bool:
        kind, _, tag = self.retry_job
        work = "failed upload" if kind == "upload" else "failed download"
        count = self.retry_count(kind=kind, names=names)

        return (
            bool(count)
            and not self.vault.uploading()
            and ask_yes_no(
                title=title,
                message=f"Retry {plural(count=count, word=work)} of release {tag}?",
                parent=self.app,
                action=title,
            )
        )

    def retry(self) -> None:
        names = self.chosen_retry()

        if self.confirm_retry(title="Retry", names=names):
            self.run(self.vault.retry_failed, names)

    def retry_all(self) -> None:
        if self.confirm_retry(title="Retry all", names=self.retry_job[1]):
            self.run(action=self.vault.retry_failed)

    # Rows that hold other rows only open and close, as Qt does on a double-click.
    def upload_row(self, item: QTreeWidgetItem) -> None:
        name = self.unit_of.get(item.data(0, Qt.ItemDataRole.UserRole))

        if name and self.tag and self.confirm_upload(title="Upload", names=[name]):
            self.run(self.vault.upload_folders, [name])

    def download_row(self, item: QTreeWidgetItem) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)

        if key in self.asset_groups and self.confirm_download(title="Download", keys=[key]):
            self.run(self.vault.download_assets, self.asset_groups[key])

    def cancel(self) -> None:
        if self.vault.uploading() and ask_yes_no(
            title="Stop GitHub job",
            message="Stop the current GitHub job?",
            parent=self.app,
            action="Stop",
            danger=True,
            keep="Keep running",
        ):
            self.vault.upload_cancel.set()

    def confirm_download(self, title: str, keys: list[str]) -> bool:
        title = self.download_text(text=title, keys=keys)
        text = f"{self.download_text(text='Download', keys=keys)} {plural(count=len(keys), word='item')} of release {self.tag} into the source folder?"
        columns, rows, total = self.asset_rows_for(keys=keys)

        return not self.vault.uploading() and confirm(
            title=title,
            question=text,
            columns=columns,
            rows=rows,
            parent=self.app,
            total=total,
        )

    def download(self) -> None:
        names = self.selected_assets()

        if names and self.confirm_download(title="Download", keys=self.chosen_keys()):
            self.run(self.vault.download_assets, names)

    def download_all(self) -> None:
        if self.confirm_download(title="Download all", keys=list(self.asset_groups)):
            self.run(action=self.vault.download_assets)

    def delete(self) -> None:
        names = self.selected_assets()
        keys = self.chosen_keys()
        text = f"This deletes {plural(count=len(keys), word='game')} from release {self.tag}. It cannot be undone."
        columns, rows, total = self.asset_rows_for(keys=keys)

        # Typed like the other two deletes, so Enter alone cannot remove files from a release.
        if (
            names
            and rows
            and not self.vault.uploading()
            and confirm_typed(
                title="Delete from release",
                message=text,
                word="delete",
                action="Delete from release",
                parent=self.app,
                table=(columns, rows, total),
            )
        ):
            self.run(self.vault.delete_release_assets, names)
