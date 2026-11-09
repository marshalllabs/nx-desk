from typing import Collection, Iterable, List, Optional, Set, Tuple

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
)

from ... import uploader
from ...schemas.presentation import TableData
from ...utils.sizes import format_size
from ...utils.text import again, plural
from ..icon_set import icon_html
from ..rows import action_text, total_text
from ..widgets.basics import fill_menu
from .release_actions import ReleaseActions
from .tree_items import children


class Selection(ReleaseActions):
    # A selected row contributes every game folder at or under it.
    def units_under(self, item: QTreeWidgetItem) -> Set[str]:
        iid = item.data(0, Qt.ItemDataRole.UserRole)

        if iid in self.unit_of:
            return {self.unit_of[iid]}

        found = set()

        for child in children(item=item):
            found |= self.units_under(item=child)

        return found

    def selected_folders(self) -> Set[str]:
        found = set()

        for item in self.tree.selectedItems():
            found |= self.units_under(item=item)

        return found

    # A game row stands for the release files shown under it.
    def chosen_keys(self) -> List[str]:
        keys = []

        # While comparing, the chosen release is the left panel.
        tree = self.compare_trees[0] if self.comparing else self.assets

        for item in tree.selectedItems():
            key = item.data(0, Qt.ItemDataRole.UserRole)
            members = (
                [key]
                if key in self.asset_groups
                else [child.data(0, Qt.ItemDataRole.UserRole) for child in children(item=item)]
            )
            keys += [member for member in members if member not in keys]

        return keys

    # Folders whose files the chosen release already holds.
    def on_release(self) -> Set[str]:
        job = self.vault.upload_snapshot()
        keys = {uploader.parts.group_key(name=asset.name) for asset in job.assets}

        return {folder.name for folder in job.folders if folder.asset in keys}

    # Release files that already have a local copy.
    def local_keys(self) -> Set[str]:
        return {folder.asset for folder in self.vault.upload_snapshot().folders}

    # "Upload" becomes "Re-upload" when every named folder is already on the release.
    def upload_text(self, text: str, names: Collection[str]) -> str:
        return again(text=text, done=bool(names) and set(names) <= self.on_release())

    # "Download" becomes "Re-download" when every named release file already has a local copy.
    def download_text(self, text: str, keys: Collection[str]) -> str:
        return again(text=text, done=bool(keys) and set(keys) <= self.local_keys())

    def selected_assets(self) -> List[str]:
        return [name for key in self.chosen_keys() for name in self.asset_groups[key]]

    def asset_rows_for(self, keys: List[str]) -> TableData:
        local = {folder.asset for folder in self.vault.upload_snapshot().folders}
        rows: List[Tuple[str, ...]] = [
            (
                key,
                f"{len(self.asset_groups[key])} parts" if len(self.asset_groups[key]) > 1 else "1 file",
                format_size(value=self.asset_sizes[key]) if self.asset_sizes[key] else "-",
                self.asset_updated[key] or "-",
                "Yes" if key in local else "No",
            )
            for key in keys
            if key in self.asset_groups
        ]
        total = sum(self.asset_sizes.get(key, 0) for key in keys)

        return TableData(
            columns=("Release file", "Files", "Size", "Updated", "Local copy"),
            rows=rows,
            total=total_text(size=total),
        )

    @property
    def comparing(self) -> bool:
        return self.bodies.currentIndex() == 1

    # A split download fails as one item, so its parts count once.
    @staticmethod
    def retry_count(kind: str, names: List[str]) -> int:
        return len(names) if kind == "upload" else len({uploader.parts.group_key(name=name) for name in names})

    # The failed ones among the chosen rows: source folders after an upload, release files after a download.
    def chosen_retry(self) -> List[str]:
        kind, names, tag = self.retry_job.kind, self.retry_job.names, self.retry_job.tag

        if tag != self.tag:
            return []

        if kind == "upload" and not self.comparing:
            chosen = self.selected_folders()

        elif kind == "download":
            chosen = set(self.selected_assets())

        else:
            return []

        return [name for name in names if name in chosen]

    # Sets the action that a button, a ▾ menu and a right-click menu all show.
    @staticmethod
    def set_action(action: QAction, text: str, count: int, enabled: bool, size: int = 0) -> None:
        action.setText(action_text(text=text, count=count, size=size))
        action.setEnabled(enabled)

    # Bytes an upload of these folders sends.
    def folder_size(self, names: Collection[str]) -> int:
        return sum(folder.size for folder in self.vault.upload_snapshot().folders if folder.name in names)

    # Bytes a download of these release files brings, parts joined.
    def asset_size(self, keys: Collection[str]) -> int:
        return sum(self.asset_sizes.get(key, 0) for key in keys)

    def paint_choice(self) -> None:
        busy = self.vault.uploading()
        # While comparing, the source folders are out of sight, so only the chosen release's files
        # can be deleted; release changes and retries still work.
        comparing = self.comparing
        tag = self.tag
        picked_folders = set() if comparing else self.selected_folders()
        folders = len(picked_folders)
        picked_keys = self.chosen_keys()
        chosen = len(picked_keys)
        shown = 0 if comparing else chosen
        self.set_action(
            action=self.upload_action,
            text=self.upload_text(text="Upload", names=picked_folders),
            count=folders,
            size=self.folder_size(names=picked_folders),
            enabled=bool(folders and tag) and not busy,
        )
        units = set(self.unit_of.values())
        self.set_action(
            action=self.upload_all_action,
            text=self.upload_text(text="Upload all", names=units),
            count=len(units),
            size=self.folder_size(names=units),
            enabled=bool(self.unit_of) and bool(tag) and not busy and not comparing,
        )
        self.set_action(
            action=self.delete_folders_action,
            text="Delete",
            count=folders,
            enabled=bool(folders) and not busy,
        )
        self.set_action(
            action=self.download_action,
            text=self.download_text(text="Download", keys=picked_keys),
            count=shown,
            size=self.asset_size(keys=picked_keys) if shown else 0,
            enabled=bool(shown) and not busy,
        )
        self.set_action(
            action=self.download_all_action,
            text=self.download_text(text="Download all", keys=list(self.asset_groups)),
            count=len(self.asset_groups),
            size=self.asset_size(keys=self.asset_groups),
            enabled=bool(self.asset_groups) and not busy and not comparing,
        )
        self.set_action(
            action=self.delete_assets_action,
            text="Delete",
            count=chosen,
            enabled=bool(chosen) and not busy,
        )
        known = tag in self.known_releases and not busy
        self.rename_action.setEnabled(known)
        self.delete_release_action.setEnabled(known)
        self.create_action.setEnabled(bool(self.repo) and not busy)
        kind, names, retry_tag = self.retry_job.kind, self.retry_job.names, self.retry_job.tag
        failed = self.retry_count(kind=kind, names=names) if retry_tag == tag else 0
        picked = self.retry_count(kind=kind, names=self.chosen_retry())
        self.set_action(action=self.retry_all_action, text="Retry all", count=failed, enabled=bool(failed) and not busy)
        self.set_action(action=self.retry_action, text="Retry chosen", count=picked, enabled=bool(picked) and not busy)
        work = "failed upload" if kind == "upload" else "failed download"
        self.failed_label.setText(f"{icon_html(name='warning')} {plural(count=failed, word=work)}")
        self.failed_label.setVisible(bool(failed))
        self.retry_button.setVisible(bool(failed))

    # Right-clicking a row offers what can be done with the chosen rows.
    def attach_menu(self, tree: QTreeWidget, entries: Iterable[Optional[QAction]]) -> None:
        shown = list(entries)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda point: self.open_menu(tree=tree, entries=shown, point=point))

    def open_menu(self, tree: QTreeWidget, entries: List[Optional[QAction]], point: QPoint) -> None:
        self.paint_choice()
        menu = fill_menu(menu=QMenu(self), entries=entries)
        menu.exec(tree.viewport().mapToGlobal(point))
        menu.deleteLater()
