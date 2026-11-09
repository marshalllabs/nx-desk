from typing import Dict, List, Optional, Set

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QTreeWidget,
    QTreeWidgetItem,
)

from ... import uploader
from ...names import game_of, shared_games
from ...schemas.github import Asset, Folder, TreeNode, UploadSnapshot
from ...utils.sizes import format_size
from ..rows import UPLOAD_STATUS, WAITING
from ..theme import COLORS
from ..widgets.basics import choice
from ..widgets.log_pane import paint_item
from ..widgets.sort_item import SortItem
from .state import UploadTabState
from .tree_items import ROW_COLORS, filter_tree


class Trees(UploadTabState):
    def count_invalid(self, nodes: List[TreeNode]) -> int:
        return sum(node.invalid + self.count_invalid(nodes=node.children) for node in nodes)

    def update_legend(self, job: UploadSnapshot, local_assets: Set[str]) -> None:
        self.source_title.setText(f"Local mods ({len(job.folders)})")
        self.release_title.setText(f"Release mods ({len(self.asset_groups)})")
        uploaded_folders = self.uploaded_folders(job=job)
        uploaded = sum(1 for folder in job.folders if folder.name in uploaded_folders)
        local = sum(1 for key in self.asset_groups if key in local_assets)
        counts = {
            "uploaded": uploaded,
            "missing": len(job.folders) - uploaded,
            "invalid": self.count_invalid(nodes=job.tree_nodes),
            "local": local,
            "orphan": len(self.asset_groups) - local,
        }

        for key, legend in self.legend.items():
            note, text = legend.label, legend.text
            note.setText(f"{text} ({counts[key]})")

    @staticmethod
    def opened(rows: Dict[str, QTreeWidgetItem]) -> Set[str]:
        return {iid for iid, item in rows.items() if item.isExpanded()}

    # A game row opens the first time it shows; after that it stays as the user left it.
    def starts_open(self, iid: str, opened: Set[str]) -> bool:
        if iid in self.known_groups:
            return iid in opened

        self.known_groups.add(iid)

        return True

    @staticmethod
    def place(
        tree: QTreeWidget,
        rows: Dict[str, QTreeWidgetItem],
        parent: Optional[str],
        item: QTreeWidgetItem,
        iid: str,
    ) -> None:
        item.setData(0, Qt.ItemDataRole.UserRole, iid)
        rows[iid] = item

        if parent is None:
            tree.addTopLevelItem(item)

        else:
            rows[parent].addChild(item)

    def paint_assets(self, job: UploadSnapshot, local_assets: Set[str]) -> None:
        # Game names come from the local folders, since release file names lose them.
        if (job.asset_list, job.tree) != self.shown_assets:
            self.shown_assets = (job.asset_list, job.tree)
            opened = self.opened(rows=self.asset_rows)
            top = self.assets.verticalScrollBar().value()
            self.assets.setSortingEnabled(False)
            self.assets.clear()
            self.asset_rows = {}
            groups: Dict[str, List[Asset]] = {}

            for asset in job.assets:
                groups.setdefault(uploader.parts.group_key(name=asset.name), []).append(asset)

            self.asset_groups = {key: [a.name for a in members] for key, members in groups.items()}
            self.asset_sizes = {key: sum(a.size for a in members) for key, members in groups.items()}
            self.asset_updated = {key: members[0].updated_at[:10] for key, members in groups.items()}
            # The label holds the folder's real name; older files without one need a local copy.
            folder_of = {folder.asset: folder.name for folder in job.folders}

            for asset in job.assets:
                folder_of.setdefault(uploader.parts.group_key(name=asset.name), asset.label or "")

            homes = {}
            expand = []

            for game, keys in shared_games(
                games={key: game_of(folder=folder_of.get(key, "")) for key in groups},
            ).items():
                iid = f"//{game}"
                size = sum(self.asset_sizes[key] for key in keys)
                updated = max(self.asset_updated[key] for key in keys)
                item = SortItem(texts=[game, format_size(value=size), updated, ""], name=game, size=size, group=True)
                self.place(tree=self.assets, rows=self.asset_rows, parent=None, item=item, iid=iid)

                if self.starts_open(iid=iid, opened=opened):
                    expand.append(item)

                homes.update(dict.fromkeys(keys, iid))

            for key in groups:
                size = self.asset_sizes[key]
                item = SortItem(texts=[key, format_size(value=size), self.asset_updated[key], ""], name=key, size=size)
                self.place(tree=self.assets, rows=self.asset_rows, parent=homes.get(key), item=item, iid=key)

            for item in expand:
                item.setExpanded(True)

            self.assets.setSortingEnabled(True)
            filter_tree(tree=self.assets, text=self.release_search.text())
            QTimer.singleShot(0, lambda: self.assets.verticalScrollBar().setValue(top))

        shown_tag = choice(box=self.release_box).strip()
        failed = (
            {uploader.parts.group_key(name=name) for name in job.retry_names}
            if job.retry_kind == "download" and job.retry_tag == shown_tag
            else set()
        )

        for key in self.asset_groups:
            fresh = any(name in job.fresh_assets for name in self.asset_groups[key])
            orphan = key not in local_assets
            state = "error" if key in failed else "fresh" if fresh else "orphan" if orphan else "local"
            row = self.asset_rows[key]
            self.color(item=row, state=state, columns=4)
            done = "Failed" if key in failed else "Not downloaded" if orphan else "Downloaded"
            row.setText(3, job.item_progress.get(key) or done)

        self.roll_up(rows=self.asset_rows, column=3, active=job.item_progress)

    @staticmethod
    def color(item: QTreeWidgetItem, state: str, columns: int) -> None:
        foreground, background = ROW_COLORS[state]
        paint_item(
            item=item,
            columns=columns,
            foreground=COLORS[foreground],
            background=COLORS[background] if background else None,
            only=columns - 1,
        )

    # Mod folders of the same game show under one row named after it. Only the view changes.
    def add_nodes(
        self,
        nodes: List[TreeNode],
        parent: Optional[str],
        opened: Set[str],
        expand: List[QTreeWidgetItem],
    ) -> None:
        leaves = {node.name: game_of(folder=node.name) for node in nodes if node.unit or node.invalid}
        homes = {}

        for game, members in shared_games(games=leaves).items():
            iid = f"{parent or ''}//{game}"
            size = sum(node.size for node in nodes if node.name in members)
            item = SortItem(texts=[game, format_size(value=size), ""], name=game, size=size, group=True)
            self.place(tree=self.tree, rows=self.rows, parent=parent, item=item, iid=iid)

            if self.starts_open(iid=iid, opened=opened):
                expand.append(item)

            homes.update(dict.fromkeys(members, iid))

        for node in nodes:
            iid = f"{parent}/{node.name}" if parent else node.name
            folder = not node.unit and not node.invalid
            texts = [node.name, format_size(value=node.size), "Invalid" if node.invalid else ""]
            item = SortItem(texts=texts, name=node.name, size=node.size, folder=folder)
            self.place(tree=self.tree, rows=self.rows, parent=homes.get(node.name, parent), item=item, iid=iid)

            if iid in opened:
                expand.append(item)

            if node.unit:
                self.unit_of[iid] = node.unit
                self.unit_iid[node.unit] = iid

            elif node.invalid:
                self.color(item=item, state="invalid", columns=3)

            else:
                self.add_nodes(nodes=node.children, parent=iid, opened=opened, expand=expand)

    # Folder and game rows can be closed, so they show what the rows inside them are doing.
    @staticmethod
    def roll_up(rows: Dict[str, QTreeWidgetItem], column: int, active: Dict[str, str]) -> None:
        shown: Dict[int, str] = {}

        # A row at work says more than one still waiting, so it goes first.
        for iid, text in sorted(active.items(), key=lambda pair: pair[1] in WAITING):
            item = rows.get(iid)
            parent = item.parent() if item else None

            while parent is not None:
                shown.setdefault(id(parent), text)
                parent = parent.parent()

        for item in rows.values():
            if isinstance(item, SortItem) and (item.folder or item.group):
                item.setText(column, shown.get(id(item), ""))

    @staticmethod
    def uploaded_folders(job: UploadSnapshot) -> Set[str]:
        assets = {asset.name: asset for asset in job.assets}

        return {
            folder.name
            for folder in job.folders
            if uploader.parts.owned_assets(stem=folder.asset.removesuffix(".zip"), assets=assets)
        }

    @staticmethod
    def unit_state(folder: Folder, uploaded_folders: Set[str]) -> str:
        if folder.status:
            return folder.status

        return "uploaded" if folder.name in uploaded_folders else "missing"

    def paint_rows(self, job: UploadSnapshot, uploaded_folders: Set[str]) -> None:
        if job.tree != self.shown_tree:
            self.shown_tree = job.tree
            opened = self.opened(rows=self.rows)
            top = self.tree.verticalScrollBar().value()
            self.tree.setSortingEnabled(False)
            self.tree.clear()
            self.rows = {}
            self.unit_of = {}
            self.unit_iid = {}
            expand: List[QTreeWidgetItem] = []
            self.add_nodes(nodes=job.tree_nodes, parent=None, opened=opened, expand=expand)

            for item in expand:
                item.setExpanded(True)

            self.tree.setSortingEnabled(True)
            filter_tree(tree=self.tree, text=self.source_search.text())
            QTimer.singleShot(0, lambda: self.tree.verticalScrollBar().setValue(top))

        for folder in job.folders:
            iid = self.unit_iid.get(folder.name)

            if iid is None:
                continue

            fresh = folder.name in job.fresh_folders and not folder.status
            state = "fresh" if fresh else self.unit_state(folder=folder, uploaded_folders=uploaded_folders)
            item = self.rows[iid]
            self.color(item=item, state=state, columns=3)
            item.setText(1, format_size(value=folder.size))
            item.setText(2, folder.progress or UPLOAD_STATUS[state])

        active = {
            self.unit_iid[folder.name]: folder.progress
            for folder in job.folders
            if folder.progress and folder.name in self.unit_iid
        }
        self.roll_up(rows=self.rows, column=2, active=active)

    def repaint_sizes(self) -> None:
        self.shown_tree = None
        self.shown_assets = None
        self.shown_compare = None
        self.painted = None
