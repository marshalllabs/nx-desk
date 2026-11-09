import collections
from typing import List

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QTreeWidget,
    QWidget,
)

from ... import uploader
from ...schemas.github import CompareRow, UploadSnapshot
from ...schemas.presentation import CompareStamp
from ...utils.sizes import format_size
from ..rows import COMPARE_STATES, compare_status, release_labels
from ..theme import COLORS
from ..widgets.basics import choice, fill_choices, label, tool
from ..widgets.log_pane import paint_item
from ..widgets.sort_item import SortItem
from .selection import Selection
from .tree_items import ROW_COLORS, make_tree


# Two releases side by side, in place of the source folders and the release.
class CompareView(Selection):
    def build_compare_body(self) -> QWidget:
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)

        # The chosen release can be reloaded and its files deleted; the other one only reloaded.
        tools = (
            (tool(action=self.refresh_action), tool(action=self.delete_assets_action, role="danger")),
            (tool(action=self.recompare_action),),
        )

        for column in (0, 1):
            head = QHBoxLayout()
            head.setSpacing(6)
            title = label(text="", role="name")
            head.addWidget(title)
            head.addSpacing(6)

            for widget in tools[column]:
                head.addWidget(widget)

            head.addStretch(1)
            notes = {}

            for state, (text, color) in COMPARE_STATES.items():
                note = label(text=text)
                note.setStyleSheet(f"color: {COLORS[color]};")
                head.addWidget(note)
                head.addSpacing(6)
                notes[state] = note

            tree = make_tree(titles=("File", "Size", "Updated", "Status"))

            # Only the chosen release can change, so the other one is for reading.
            if column == 0:
                tree.itemSelectionChanged.connect(self.paint_choice)
                self.attach_menu(tree=tree, entries=(self.delete_assets_action, None, self.refresh_action))

            else:
                tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)

            tree.header().resizeSection(2, 110)
            tree.header().resizeSection(3, 260)
            grid.addLayout(head, 0, column)
            grid.addWidget(tree, 1, column)
            self.compare_titles.append(title)
            self.compare_notes.append(notes)
            self.compare_trees.append(tree)

        return body

    def start_compare(self) -> None:
        self.run(self.vault.load_compare, choice(box=self.compare_box))

    def stop_compare(self) -> None:
        self.vault.close_compare()

    # One button starts and stops comparing; its checked look shows which.
    def toggle_compare(self) -> None:
        if self.comparing:
            self.stop_compare()

        else:
            self.start_compare()

        self.compare_button.setChecked(self.comparing)

    # Every release but the chosen one, which it cannot be compared with. The pick stays when it
    # still can, else the latest or first of the others.
    def fill_compare_box(self) -> None:
        others = [tag for tag in self.known_releases if tag != self.tag]
        kept = self.compared or choice(box=self.compare_box)
        fill_choices(
            box=self.compare_box,
            choices=others,
            current=kept if kept in others else next(iter(others), ""),
            labels=release_labels(latest=self.latest_release),
        )

    # Picking another release while comparing compares with it at once.
    def compare_chosen(self, _index: int) -> None:
        if self.comparing:
            self.start_compare()

    def paint_compare(self, job: UploadSnapshot) -> None:
        comparing = bool(job.compare_tag)
        self.compared = job.compare_tag
        self.bodies.setCurrentIndex(1 if comparing else 0)
        self.compare_button.setChecked(comparing)
        self.compare_button.setText("Stop" if comparing else "Compare")
        self.compare_button.setToolTip("Stop comparing" if comparing else "Compare the chosen release with this one")

        if not comparing:
            self.shown_compare = None

            return

        key = CompareStamp(assets=job.asset_list, compared=job.compare_list, tag=self.tag)

        if key == self.shown_compare:
            return

        self.shown_compare = key
        comparison = uploader.compare.compare_releases(left=job.assets, right=job.compare_assets)
        left = comparison.left
        right = comparison.right

        for index, (tag, rows) in enumerate(iterable=((self.tag, left), (job.compare_tag, right))):
            self.compare_titles[index].setText(f"Release {tag}")
            counts = collections.Counter(row.state for row in rows)

            for state, note in self.compare_notes[index].items():
                note.setText(f"{COMPARE_STATES[state][0]} ({counts[state]})")

            self.fill_compare(tree=self.compare_trees[index], rows=rows)

    @staticmethod
    def fill_compare(tree: QTreeWidget, rows: List[CompareRow]) -> None:
        top = tree.verticalScrollBar().value()
        tree.setSortingEnabled(False)
        tree.clear()

        for row in rows:
            status = compare_status(row=row)
            texts = [row.key, format_size(value=row.size), row.updated, status]
            item = SortItem(texts=texts, name=row.key, size=row.size)
            item.setData(0, Qt.ItemDataRole.UserRole, row.key)
            item.setToolTip(0, "\n".join(row.files))
            item.setToolTip(3, status)
            tree.addTopLevelItem(item)
            foreground, background = ROW_COLORS[row.state]
            paint_item(
                item=item,
                columns=len(texts),
                foreground=COLORS[foreground],
                background=COLORS[background] if background else None,
                only=len(texts) - 1,
            )

        tree.setSortingEnabled(True)
        QTimer.singleShot(0, lambda: tree.verticalScrollBar().setValue(top))
