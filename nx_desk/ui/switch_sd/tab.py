import threading
from typing import TYPE_CHECKING, List, Optional, Set

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QProgressBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...schemas.switch_sd import SDSnapshot, SDTitle, SwitchCard
from ...utils.sizes import format_size
from ..rows import picked_text
from ..style import mono_font, set_role
from ..theme import SPACE
from ..widgets.basics import button, clear_on_escape, copy_text, focus_box, label
from ..widgets.choice_popup import ChoicePopup
from .copy_button import CopyTitleButton
from .volumes import mounted_volumes

if TYPE_CHECKING:
    from ..app import App


class SwitchSDTab(QWidget):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self.vault = app.vault
        self.polling = False
        self.scan_pending = False
        self.phase = "idle"
        self.categories: Set[str] = {"Game"}
        self.shown_categories: Optional[Set[str]] = None
        self.category_manual = False
        self.category_root = ""
        self.cards: List[SwitchCard] = []
        self.shown_titles: Optional[List[SDTitle]] = None
        layout = QVBoxLayout(self)
        layout.setSpacing(SPACE["sm"])
        layout.setContentsMargins(SPACE["lg"], SPACE["sm"], SPACE["lg"], SPACE["sm"])
        top = QHBoxLayout()
        top.addWidget(label(text="SD Card", role="muted"))
        self.card_box = QComboBox()
        self.card_box.setMinimumContentsLength(30)
        self.card_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.card_box.setAccessibleName("Detected Switch CFW card")
        self.card_box.currentIndexChanged.connect(self.choose_card)
        top.addWidget(self.card_box, 1)
        self.refresh_button = button(text="Scan card", action=lambda: self.poll(force=True))
        top.addWidget(self.refresh_button)
        self.cancel_button = button(text="Cancel", action=self.vault.cancel_switch_job)
        top.addWidget(self.cancel_button)
        layout.addLayout(top)
        self.status = label(text="", role="muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        hint = label(
            text="Card contents are mods, not proof that games are installed. Target game versions come from mod metadata.",
            role="muted",
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(SPACE["sm"])
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search Title ID or name")
        self.search.setAccessibleName("Search Switch card content")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_rows)
        clear_on_escape(box=self.search)
        filters = QHBoxLayout()
        filters.setSpacing(SPACE["sm"])
        filters.addWidget(self.search, 1)
        self.category_button = button(text="Category")
        self.category_button.setAccessibleName("Filter card content by category")
        self.category_popup = ChoicePopup(anchor=self.category_button, idle_text="All categories")
        self.category_popup.toggled.connect(self.choose_category)
        self.category_popup.cleared.connect(self.clear_categories)
        self.category_button.clicked.connect(self.category_popup.open)
        filters.addWidget(self.category_button)
        layout.addLayout(filters)
        self.card_tree = self.table(
            titles=[
                "Game / content",
                "Title ID",
                "Category",
                "Type",
                "Size",
                "Metadata status",
                "Mod version",
                "Target game",
                "Action",
            ],
        )
        copy = QAction("Copy Title ID", self.card_tree)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        copy.triggered.connect(self.copy_selected_titles)
        self.card_tree.addAction(copy)
        group = QGroupBox("Content on selected card")
        body = QVBoxLayout(group)
        body.addWidget(self.card_tree)
        layout.addWidget(group, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.paint(job=self.vault.switch_snapshot())
        QTimer.singleShot(0, self.poll)

    @staticmethod
    def table(titles: List[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(titles)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setUniformRowHeights(True)
        tree.setSortingEnabled(True)
        tree.sortItems(0, Qt.SortOrder.AscendingOrder)
        tree.header().setStretchLastSection(False)
        tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for column in range(1, len(titles)):
            tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        return tree

    def poll(self, force: bool = False) -> None:
        if self.polling:
            self.scan_pending = self.scan_pending or force

            return

        self.polling = True

        def worker() -> None:
            try:
                self.vault.refresh_switch_cards(volumes=mounted_volumes(), force=force)

            finally:
                self.app.later(action=self.polled)

        threading.Thread(target=worker, daemon=True).start()

    def polled(self) -> None:
        self.polling = False
        self.paint(job=self.vault.switch_snapshot())

        if self.scan_pending:
            self.scan_pending = False
            self.poll(force=True)

    def choose_card(self, _index: int) -> None:
        self.vault.select_switch_card(root=str(self.card_box.currentData() or ""))
        self.poll(force=True)

    def selected_card(self) -> Optional[SwitchCard]:
        root = self.card_box.currentData()

        return next((card for card in self.cards if str(card.root) == root), None)

    def controls(self) -> None:
        card = self.selected_card()
        busy = self.phase != "idle"
        self.card_box.setEnabled(not busy)
        self.refresh_button.setEnabled(not busy and card is not None)
        self.cancel_button.setVisible(self.phase != "idle")

    def paint(self, job: SDSnapshot) -> None:
        self.phase = job.phase
        root = job.selected

        if root != self.category_root:
            self.category_root = root
            self.category_manual = False

        if not self.category_manual and job.phase == "idle" and not job.failed:
            self.categories = {"Game"} if any(row.category == "Game" for row in job.titles) else set()

        self.paint_categories()

        if job.cards != self.cards or self.card_box.currentData() != root:
            self.cards = job.cards

            with QSignalBlocker(self.card_box):
                self.card_box.clear()
                if not job.cards:
                    self.card_box.addItem("No SD card detected", "")

                for card in job.cards:
                    suffix = " · Read-only" if card.read_only else ""
                    self.card_box.addItem(f"{card.label or card.root.name} · {card.root}{suffix}", str(card.root))

                self.card_box.setCurrentIndex(max(0, self.card_box.findData(root)))

        self.status.setText(job.message)
        set_role(widget=self.status, role="error" if job.failed else "muted")
        self.progress.setVisible(job.phase != "idle")
        self.progress.setRange(0, 0)

        if job.titles != self.shown_titles:
            self.shown_titles = job.titles
            self.card_tree.clear()

            for row in job.titles:
                item = QTreeWidgetItem(
                    self.card_tree,
                    [
                        row.name,
                        row.title_id,
                        row.category,
                        ", ".join(row.kinds),
                        format_size(value=row.size),
                        row.status,
                        row.mod_version,
                        row.target_game,
                    ],
                )

                item.setFont(1, mono_font())

                for column in range(self.card_tree.columnCount()):
                    item.setToolTip(column, item.text(column))

                action = CopyTitleButton(title_id=row.title_id)
                column = self.card_tree.columnCount() - 1
                item.setSizeHint(column, QSize(action.width() + SPACE["sm"], action.height() + SPACE["xs"]))
                self.card_tree.setItemWidget(item, column, action)

        self.filter_rows()
        self.controls()

    def copy_selected_titles(self) -> None:
        rows = [
            row
            for index in range(self.card_tree.topLevelItemCount())
            if (row := self.card_tree.topLevelItem(index)) is not None and row.isSelected() and not row.isHidden()
        ]

        if not rows:
            return

        copy_text(text="\n".join(row.text(1) for row in rows))

        for row in rows:
            action = self.card_tree.itemWidget(row, self.card_tree.columnCount() - 1)

            if isinstance(action, CopyTitleButton):
                action.mark_copied()

    def paint_categories(self) -> None:
        if self.shown_categories == self.categories:
            return

        self.shown_categories = self.categories.copy()
        choices = [
            ("Game", "Game"),
            ("System content", "System content"),
            ("Sysmodule", "Sysmodule"),
            ("", "Unclassified"),
        ]
        self.category_popup.set_choices(choices=choices, picked=self.categories)
        names = [name for key, name in choices if key in self.categories]
        self.category_button.setText(picked_text(title="Category", picked=names))

    def choose_category(self, name: str, chosen: bool) -> None:
        self.category_manual = True

        if chosen:
            self.categories.add(name)

        else:
            self.categories.discard(name)

        self.paint_categories()
        self.filter_rows()

    def clear_categories(self) -> None:
        self.category_manual = True
        self.categories.clear()
        self.paint_categories()
        self.filter_rows()

    def filter_rows(self) -> None:
        query = self.search.text().strip().casefold()

        tree = self.card_tree

        for index in range(tree.topLevelItemCount()):
            row = tree.topLevelItem(index)

            if row is None:
                continue

            hidden = (
                bool(query)
                and query not in " ".join(row.text(column) for column in range(tree.columnCount())).casefold()
            )
            hidden = hidden or (bool(self.categories) and row.text(2) not in self.categories)
            row.setHidden(hidden)

            if hidden:
                row.setSelected(False)

    def focus_search(self) -> None:
        focus_box(box=self.search)
