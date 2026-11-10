import threading
from typing import TYPE_CHECKING, List, Optional, Set

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QImage, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...catalog.homebrews import find_homebrews
from ...schemas.homebrew import Homebrew, HomebrewSnapshot
from ...system import open_in_system
from ..cards.grid import CardGrid
from ..cards.thumbs import CoverThumbs
from ..list_art import ListArt
from ..rows import SortState, picked_text
from ..style import set_role
from ..theme import SPACE
from ..widgets.basics import button, clear_on_escape, copy_text, fill_menu, focus_box, label, menu_button
from ..widgets.choice_popup import ChoicePopup
from ..widgets.resize_watch import ResizeWatch
from ..widgets.spinner import Spinner
from .detail import HomebrewDetail
from .model import COLUMNS, HomebrewModel, cell

if TYPE_CHECKING:
    from ..app import App


class HomebrewsTab(QWidget):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.vault = app.vault
        self.rows: List[Homebrew] = []
        self.selected: Optional[Homebrew] = None
        self.groups: Set[str] = set()
        self.categories: Set[str] = set()
        self.order = SortState(column="name")
        self.view = self.vault.homebrews_view
        self.version: Optional[int] = None
        self.job = self.vault.homebrew_snapshot()
        self.art = ListArt(vault=self.vault, art_dir=self.vault.homebrews_art_dir)
        self.art_version = self.art.version_of()
        self.art_timer = QTimer(self)
        self.art_timer.setSingleShot(True)
        self.art_timer.setInterval(250)
        self.art_timer.timeout.connect(self.ask_art)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addLayout(self.build_toolbar())
        self.status = label(role="muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.spinner = Spinner(target=self.status)
        layout.addWidget(self.status)
        layout.addWidget(self.build_body(), 1)
        self.fill()

    def build_toolbar(self) -> QHBoxLayout:
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(label(text="Search", role="muted"))
        self.query = QLineEdit()
        self.query.setFixedWidth(320)
        self.query.setToolTip("Ctrl+F to search, Esc to clear")
        self.query.setPlaceholderText("Name, description or author")
        self.query.setClearButtonEnabled(True)
        self.query.setAccessibleName("Search homebrews")
        self.query.textChanged.connect(self.fill)
        clear_on_escape(box=self.query)
        top.addWidget(self.query)
        self.group_button = button(text="Group")
        self.group_popup = ChoicePopup(anchor=self.group_button, idle_text="All groups")
        self.group_popup.toggled.connect(lambda name, chosen: self.toggle_filter(name=name, chosen=chosen, group=True))
        self.group_popup.cleared.connect(lambda: self.clear_filter(group=True))
        self.group_button.clicked.connect(self.group_popup.open)
        top.addWidget(self.group_button)
        self.type_button = button(text="Type")
        self.type_popup = ChoicePopup(anchor=self.type_button, idle_text="All types")
        self.type_popup.toggled.connect(lambda name, chosen: self.toggle_filter(name=name, chosen=chosen, group=False))
        self.type_popup.cleared.connect(lambda: self.clear_filter(group=False))
        self.type_button.clicked.connect(self.type_popup.open)
        top.addWidget(self.type_button)
        top.addStretch(1)
        self.sort_actions = {name: self.sort_action(name=name, title=title) for name, title, _ in COLUMNS}
        self.direction_actions = {
            True: self.direction_action(ascending=True, title="Ascending"),
            False: self.direction_action(ascending=False, title="Descending"),
        }
        self.sort_button = menu_button(
            text="Sort",
            entries=[*self.sort_actions.values(), None, *self.direction_actions.values()],
            tip="Sort homebrews",
        )
        self.sort_button.menu().aboutToShow.connect(self.paint_controls)
        top.addWidget(self.sort_button)
        self.view_actions = {
            name: self.view_action(name=name, title=title) for name, title in (("list", "List"), ("grid", "Grid"))
        }
        self.view_button = menu_button(text="", entries=self.view_actions.values(), glyph="menu", tip="Change view")
        self.view_button.menu().aboutToShow.connect(self.paint_controls)
        top.addWidget(self.view_button)
        self.refresh_button = button(text="Refresh", action=lambda: self.load(force=True))
        top.addWidget(self.refresh_button)

        return top

    def build_body(self) -> QWidget:
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(SPACE["md"])
        self.model = HomebrewModel(order=self.order)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(36)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, (_, _, width) in enumerate(iterable=COLUMNS):
            header.setSectionResizeMode(
                index,
                QHeaderView.ResizeMode.Interactive if width else QHeaderView.ResizeMode.Stretch,
            )

            if width:
                header.resizeSection(index, width)

        header.sectionClicked.connect(self.sort_by)
        thumbs = CoverThumbs(files=self.art.files_of, version=self.art.version_of, settled=self.art.settled_key)
        self.grid = CardGrid(model=self.model, thumbs=thumbs, changes=self.art.changes)
        self.grid.setSelectionModel(self.table.selectionModel())
        self.table.selectionModel().currentChanged.connect(self.row_changed)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.stack.addWidget(self.grid)
        self.empty = label(text="No entries loaded", role="muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.empty)
        body.addWidget(self.stack)
        self.detail = HomebrewDetail()
        self.detail.open_button.clicked.connect(self.open_page)
        body.addWidget(self.detail)
        body.setStretchFactor(0, 1)
        body.setSizes([900, 320])
        self.open_action = QAction("Open page", self)
        self.open_action.triggered.connect(self.open_page)
        self.copy_action = QAction("Copy links", self)
        self.copy_action.triggered.connect(self.copy)

        for view in (self.table, self.grid):
            view.doubleClicked.connect(self.open_page)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(self.open_menu)
            view.verticalScrollBar().valueChanged.connect(lambda _: self.art_timer.start())

        ResizeWatch(widget=self.table.viewport(), changed=self.fit_columns)

        return body

    def fit_columns(self) -> None:
        width = self.table.viewport().width()
        self.table.setColumnHidden(4, width < 850)
        self.table.setColumnHidden(2, width < 650)
        self.table.setColumnHidden(3, width < 550)
        self.art_timer.start()

    def focus_search(self) -> None:
        focus_box(box=self.query)

    def fill_menus(self) -> None:
        groups = sorted({group for row in self.rows for group in row.groups}, key=str.casefold)
        categories = sorted({row.category for row in self.rows if row.category}, key=str.casefold)
        self.groups &= set(groups)
        self.categories &= set(categories)
        self.group_popup.set_choices(choices=[(name, name) for name in groups], picked=self.groups)
        self.type_popup.set_choices(choices=[(name, name) for name in categories], picked=self.categories)

    def toggle_filter(self, name: str, chosen: bool, group: bool) -> None:
        values = self.groups if group else self.categories

        if chosen:
            values.add(name)

        else:
            values.discard(name)

        self.fill()

    def clear_filter(self, group: bool) -> None:
        (self.groups if group else self.categories).clear()
        self.fill_menus()
        self.fill()

    def load(self, force: bool = False) -> None:
        if self.vault.homebrew_snapshot().loading:
            return

        if force:
            self.query.blockSignals(True)
            self.query.clear()
            self.query.blockSignals(False)
            self.groups.clear()
            self.categories.clear()
            self.selected = None
            self.fill_menus()
            self.fill()

        threading.Thread(target=self.vault.load_homebrews, kwargs={"force": force}, daemon=True).start()

    def fill(self) -> None:
        candidates = [
            row
            for row in self.rows
            if (not self.groups or self.groups.intersection(row.groups))
            and (not self.categories or row.category in self.categories)
        ]
        found = sorted(
            find_homebrews(rows=candidates, query=self.query.text()),
            key=lambda row: cell(row=row, column=self.order.column).casefold(),
            reverse=not self.order.ascending,
        )
        keep = self.selected.id if self.selected else None
        self.model.set_rows(rows=found)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)
        self.selected = None

        if found:
            row = next((index for index, entry in enumerate(iterable=found) if entry.id == keep), 0)
            self.table.selectionModel().setCurrentIndex(
                self.model.index(row, 0),
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
            )

        self.paint_detail()
        self.empty.setText("No entries match these filters" if self.rows else "No entries loaded")
        self.paint_controls()
        self.paint_status()
        self.art_timer.start()

    def current_view(self) -> QAbstractItemView:
        return self.grid if self.view == "grid" else self.table

    def row_changed(self) -> None:
        index = self.current_view().currentIndex().row()
        self.selected = self.model.rows[index] if 0 <= index < len(self.model.rows) else None
        self.paint_detail()
        self.art_timer.start()

    def paint(self, job: HomebrewSnapshot) -> None:
        self.job = job

        if job.version != self.version:
            self.version = job.version
            self.rows = job.rows
            self.fill_menus()
            self.fill()

        self.paint_status()
        version = self.art.version_of()

        if version != self.art_version:
            self.art_version = version
            self.art_timer.start()

        self.paint_detail()

    def paint_detail(self) -> None:
        self.detail.show_entry(row=self.selected, banner=self.picture(), needs_key=self.art.needs_key())

    def picture(self) -> Optional[QImage]:
        if self.selected is None:
            return None

        banner = self.art.banner(item=self.selected)

        if banner is None and self.art.settled(item=self.selected):
            return self.art.placeholder(icon_name="cpu")

        return banner

    def visible_entries(self) -> List[Homebrew]:
        if self.view == "grid":
            start, end = self.grid.shown_rows(total=len(self.model.rows))

            return self.model.rows[start : end + 4]

        first = self.table.rowAt(0)

        if first < 0:
            return []

        last = self.table.rowAt(self.table.viewport().height() - 1)
        last = len(self.model.rows) - 1 if last < 0 else last

        return self.model.rows[first : last + 5]

    def ask_art(self) -> None:
        if not self.isVisible():
            return

        chosen = [self.selected] if self.selected else []
        wanted = chosen + self.visible_entries()
        self.art.want(items=list({row.id: row for row in wanted}.values()))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.art_timer.start()

    def paint_status(self) -> None:
        self.refresh_button.setEnabled(not self.job.loading)

        if self.job.loading:
            self.spinner.start(text="Loading Homebrews…")

            return

        self.spinner.stop()
        set_role(widget=self.status, role="error" if self.job.error else "muted")
        self.status.setText(self.job.error or f"{len(self.model.rows):,} of {len(self.rows):,} homebrews")

    def sort_action(self, name: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.choose_sort(name=name))

        return action

    def choose_sort(self, name: str) -> None:
        self.order.choose(column=name)
        self.fill()

    def sort_by(self, index: int) -> None:
        self.order.toggle(column=COLUMNS[index][0])
        self.fill()

    def direction_action(self, ascending: bool, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_direction(ascending=ascending))

        return action

    def set_direction(self, ascending: bool) -> None:
        self.order.set_direction(ascending=ascending)
        self.fill()

    def view_action(self, name: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_view(view=name))

        return action

    def set_view(self, view: str) -> None:
        self.view = view
        self.vault.set_homebrews_view(view=view)
        self.paint_controls()
        self.art_timer.start()

    def paint_controls(self) -> None:
        self.stack.setCurrentIndex((1 if self.view == "grid" else 0) if self.model.rows else 2)
        self.group_button.setText(picked_text(title="Group", picked=sorted(self.groups)))
        self.type_button.setText(picked_text(title="Type", picked=sorted(self.categories)))
        title = {name: title for name, title, _ in COLUMNS}[self.order.column]
        self.sort_button.setText(self.order.title(column=self.order.column, text=f"Sort: {title}"))

        for name, action in self.sort_actions.items():
            action.setChecked(name == self.order.column)

        for ascending, action in self.direction_actions.items():
            action.setChecked(ascending == self.order.ascending)

        for name, action in self.view_actions.items():
            action.setChecked(name == self.view)

    def open_page(self) -> None:
        if self.selected and self.selected.url:
            open_in_system(path=self.selected.url)

    def copy(self) -> None:
        indices = {index.row() for index in self.current_view().selectionModel().selectedIndexes()}
        links = [self.model.rows[index].url for index in sorted(indices) if self.model.rows[index].url]

        if links:
            copy_text(text="\n".join(links))

    def open_menu(self, point: QPoint) -> None:
        self.open_action.setEnabled(bool(self.selected and self.selected.url))
        self.copy_action.setEnabled(bool(self.current_view().selectionModel().selectedIndexes()))
        menu = fill_menu(menu=QMenu(self), entries=(self.open_action, self.copy_action))
        menu.exec(self.current_view().viewport().mapToGlobal(point))
        menu.deleteLater()
