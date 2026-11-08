import functools
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QItemSelectionModel, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QImage, QKeySequence, QShortcut, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...catalog.ports import find_ports, platform_counts
from ...schemas.port import Port, PortSnapshot
from ...system import open_in_system
from ...utils.text import plural
from ..cards.grid import CardGrid
from ..cards.thumbs import CoverThumbs
from ..list_art import ListArt
from ..rows import SortState, picked_text
from ..style import set_role
from ..theme import SPACE
from ..widgets.basics import button, clear_on_escape, copy_text, fill_menu, focus_box, label, menu_button
from ..widgets.choice_popup import ChoicePopup
from ..widgets.overlay import Overlay
from ..widgets.resize_watch import ResizeWatch
from ..widgets.spinner import Spinner
from .detail import PortDetail
from .model import COLUMNS, HIDE_BELOW, ROW_HEIGHT, PortModel, cell

if TYPE_CHECKING:
    from ..app import App

KINDS = (("", "All"), ("port", "Ports"), ("emulator", "Emulators"))
VIEWS = (("list", "List"), ("grid", "Grid"))
# The grid has no column headers, so a menu sorts it by the same columns.
SORTS = tuple((name, title) for name, title, _ in COLUMNS)
# The pause before the art is asked for, so a burst of changes (typing, scrolling) restarts it once.
ART_DELAY = 250
# Rows past the last one in view that go right after it in the order art is fetched.
ART_LOOKAHEAD = 4
DETAIL_WIDTH = 440


class PortsTab(QWidget):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self.vault = app.vault
        self.version: int | None = None
        self.ports: list[Port] = []
        self.kind = ""
        self.platforms: set[str] = set()
        self.selected: Port | None = None
        self.sort = SortState(column="name")
        self.view = self.vault.ports_view
        self.sort_actions: dict[str, QAction] = {}
        self.sort_direction_actions: dict[bool, QAction] = {}
        self.view_actions: dict[str, QAction] = {}
        self.art = ListArt(vault=self.vault, art_dir=self.vault.ports_art_dir, port_cards=True)
        self.art_timer = QTimer(self)
        self.art_timer.setSingleShot(True)
        self.art_timer.setInterval(ART_DELAY)
        self.art_timer.timeout.connect(self.ask_art)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addLayout(self.build_toolbar())
        self.status = label(text="", role="muted")
        self.spinner = Spinner(target=self.status)
        layout.addWidget(self.status)
        layout.addWidget(self.build_body(), 1)
        self.build_actions()
        self.paint_buttons()
        self.paint_views()

    def build_toolbar(self) -> QHBoxLayout:
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(label(text="Search", role="muted"))
        self.query = QLineEdit()
        self.query.setFixedWidth(320)
        self.query.textChanged.connect(self.fill)
        self.query.setPlaceholderText("Name, platform or repository")
        self.query.setToolTip("Ctrl+F to search, Esc to clear")
        self.query.setClearButtonEnabled(True)
        clear_on_escape(box=self.query)
        top.addWidget(self.query)
        self.platform_button = button(text="Platform")
        self.platform_popup = ChoicePopup(anchor=self.platform_button, idle_text="All platforms")
        self.platform_popup.toggled.connect(self.toggle_platform)
        self.platform_popup.cleared.connect(self.clear_platforms)
        self.platform_button.clicked.connect(self.platform_popup.open)
        top.addWidget(self.platform_button)
        top.addSpacing(10)
        self.buttons: dict[str, QPushButton] = {}

        for kind, _ in KINDS:
            choice = button(text="", action=functools.partial(self.choose_kind, kind))

            choice.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            top.addWidget(choice)
            self.buttons[kind] = choice

        top.addStretch(1)
        self.sort_actions = {name: self.sort_action(column=name, title=title) for name, title in SORTS}
        self.sort_direction_actions = {
            True: self.sort_direction_action(ascending=True, title="Ascending"),
            False: self.sort_direction_action(ascending=False, title="Descending"),
        }
        self.sort_button = menu_button(
            text="Sort",
            entries=[*self.sort_actions.values(), None, *self.sort_direction_actions.values()],
            tip="Sort the grid",
        )
        self.sort_button.menu().aboutToShow.connect(self.paint_sort_menu)
        top.addWidget(self.sort_button)
        self.view_actions = {view: self.view_action(view=view, title=title) for view, title in VIEWS}
        self.view_button = menu_button(
            text="",
            entries=self.view_actions.values(),
            tip="Change view",
            glyph="menu",
        )
        self.view_button.menu().aboutToShow.connect(self.paint_views)
        top.addWidget(self.view_button)

        top.addSpacing(10)
        self.refresh_button = button(text="Refresh", action=lambda: self.load(force=True))
        top.addWidget(self.refresh_button)

        return top

    # The list and the detail pane share a splitter, so the user picks how wide each one is.
    def build_body(self) -> QWidget:
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(SPACE["md"])
        self.model = PortModel(sort=self.sort)
        table = self.table = QTableView()
        table.setModel(self.model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, (_, _, width) in enumerate(COLUMNS):
            if width:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(index, width)
            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

        header.sectionClicked.connect(self.sort_by)
        thumbs = CoverThumbs(files=self.art.files_of, version=self.art.version_of, settled=self.art.settled_key)
        self.grid = CardGrid(model=self.model, thumbs=thumbs, changes=self.art.changes)
        self.empty = self.wire_view(view=table)
        self.grid_empty = self.wire_view(view=self.grid)
        # The table and the grid take turns in one place.
        self.stack = QStackedWidget()
        self.stack.addWidget(table)
        self.stack.addWidget(self.grid)
        # A shrinking window takes room from the detail pane first, so the list stays usable.
        self.stack.setMinimumWidth(480)
        self.detail = PortDetail()
        self.detail.repo_button.clicked.connect(self.open_page)
        self.detail.thread_button.clicked.connect(self.open_thread)
        body.addWidget(self.stack)
        body.addWidget(self.detail)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 0)
        body.setSizes([1000, DETAIL_WIDTH])
        # The table's own size decides, whether the window or the splitter changed it.
        ResizeWatch(widget=table.viewport(), changed=self.fit_columns)
        ResizeWatch(widget=self.grid.viewport(), changed=lambda: self.art_timer.start())

        return body

    # What both views do alike: the chosen row, scrolling, opening, the menu and the empty message.
    def wire_view(self, view: QAbstractItemView) -> QLabel:
        view.selectionModel().currentRowChanged.connect(self.row_changed)
        view.verticalScrollBar().valueChanged.connect(lambda _: self.art_timer.start())
        view.doubleClicked.connect(lambda _: self.open_page())
        enter = QShortcut(QKeySequence(Qt.Key.Key_Return), view)
        enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        enter.activated.connect(self.open_page)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self.open_menu)
        empty = label(text="", role="muted", parent=view.viewport())
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.hide()
        Overlay(viewport=view.viewport(), message=empty)

        return empty

    def build_actions(self) -> None:
        self.page_action = QAction("Open page", self)
        self.page_action.triggered.connect(lambda _=False: self.open_page())
        self.thread_action = QAction("Open thread", self)
        self.thread_action.triggered.connect(lambda _=False: self.open_thread())
        self.copy_action = QAction("Copy link", self)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.copy_action.triggered.connect(lambda _=False: self.copy())
        self.table.addAction(self.copy_action)
        self.grid.addAction(self.copy_action)

    def focus_search(self) -> None:
        focus_box(box=self.query)

    def load(self, force: bool = False) -> None:
        if force:
            self.reset_filters()

        threading.Thread(target=self.vault.load_ports, args=(force,), daemon=True).start()

    def reset_filters(self) -> None:
        self.query.blockSignals(True)
        self.query.clear()
        self.query.blockSignals(False)
        self.kind = ""
        self.platforms.clear()
        self.selected = None
        self.fill_platform_menu()
        self.paint_buttons()
        self.fill()

    # Columns the detail pane also shows go first when the list gets narrow, and the status column
    # only shows once an entry has one.
    def fit_columns(self) -> None:
        width = self.table.viewport().width()
        has_status = any(port.status for port in self.ports)

        for index, (name, _, _) in enumerate(COLUMNS):
            limit = HIDE_BELOW.get(name)
            hidden = (name == "status" and not has_status) or (limit is not None and width < limit)
            self.table.setColumnHidden(index, hidden)

        # A taller or shorter list shows other rows.
        self.art_timer.start()

    def choose_kind(self, kind: str) -> None:
        self.kind = kind
        self.paint_buttons()
        self.fill()

    def toggle_platform(self, platform: str, selected: bool) -> None:
        if selected:
            self.platforms.add(platform)
        else:
            self.platforms.discard(platform)

        self.paint_platform_button()
        self.fill()

    def clear_platforms(self) -> None:
        self.platforms.clear()
        self.fill_platform_menu()
        self.fill()

    def fill_platform_menu(self) -> None:
        self.platform_popup.set_choices(
            choices=[(name, f"{name} ({count:,})") for name, count in platform_counts(rows=self.ports)],
            picked=self.platforms,
        )
        self.paint_platform_button()

    def paint_platform_button(self) -> None:
        self.platform_button.setText(picked_text(title="Platform", picked=sorted(self.platforms, key=str.lower)))

    def paint_buttons(self) -> None:
        for kind, text in KINDS:
            count = sum(port.kind == kind or not kind for port in self.ports)
            self.buttons[kind].setText(f"{text} ({count:,})")
            # A filter, not an action: the same quiet segmented look as the List and Log pair.
            chosen = kind == self.kind
            set_role(widget=self.buttons[kind], role="segment-on" if chosen else "segment")
            self.buttons[kind].setAccessibleName(f"{text} ({count:,})" + (", shown" if chosen else ""))

    def sort_by(self, column: int) -> None:
        self.sort.toggle(column=COLUMNS[column][0])
        self.fill()

    # Filters and sorting rebuild the rows; the chosen entry stays chosen when it is still listed.
    def fill(self) -> None:
        rows = [
            port
            for port in self.ports
            if (not self.kind or port.kind == self.kind) and (not self.platforms or port.platform in self.platforms)
        ]
        found = find_ports(rows=rows, query=self.query.text())
        found = sorted(
            found,
            key=lambda port: cell(port=port, column=self.sort.column).casefold(),
            reverse=not self.sort.ascending,
        )
        keep = self.selected.id if self.selected else None
        self.model.set_rows(rows=found)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)
        row = next((number for number, port in enumerate(found) if port.id == keep), 0)

        if found:
            self.select_row(row=row)
        else:
            self.selected = None

        message = "No entries match these filters" if self.ports else "No entries loaded"

        for empty, view in ((self.empty, self.table), (self.grid_empty, self.grid)):
            empty.setText(message)
            empty.setGeometry(view.viewport().rect())
            empty.setVisible(not found)

        self.paint_sort_button()
        self.paint_status(job=self.vault.port_snapshot())

    def current_view(self) -> QAbstractItemView:
        return self.grid if self.view == "grid" else self.table

    def select_row(self, row: int) -> None:
        index = self.model.index(row, 0)
        flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        view = self.current_view()
        view.selectionModel().setCurrentIndex(index, flags)
        view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def set_view(self, view: str) -> None:
        self.view = view
        self.vault.set_ports_view(view=view)
        self.stack.setCurrentIndex(1 if view == "grid" else 0)
        self.paint_views()
        row = next(
            (number for number, port in enumerate(self.model.rows) if self.selected and port.id == self.selected.id),
            -1,
        )

        # The other view was hidden while the rows changed, so the chosen row is chosen there again.
        if row >= 0:
            self.select_row(row=row)

        self.art_timer.start()

    def paint_views(self) -> None:
        self.stack.setCurrentIndex(1 if self.view == "grid" else 0)
        self.sort_button.setVisible(self.view == "grid")

        for view, action in self.view_actions.items():
            action.setChecked(view == self.view)

    def sort_action(self, column: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.choose_sort_column(column=column))

        return action

    def sort_direction_action(self, ascending: bool, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_sort_direction(ascending=ascending))

        return action

    def view_action(self, view: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_view(view=view))

        return action

    def paint_sort_menu(self) -> None:
        for column, action in self.sort_actions.items():
            action.setChecked(column == self.sort.column)

        for ascending, action in self.sort_direction_actions.items():
            action.setChecked(ascending == self.sort.ascending)

    def choose_sort_column(self, column: str) -> None:
        self.sort.choose(column=column)
        self.fill()

    def set_sort_direction(self, ascending: bool) -> None:
        self.sort.set_direction(ascending=ascending)
        self.fill()

    # A table header click keeps the familiar ascending/descending toggle.
    def sort_column(self, column: str) -> None:
        self.sort.toggle(column=column)
        self.fill()

    def paint_sort_button(self) -> None:
        titles = dict(SORTS)
        self.sort_button.setText(self.sort.title(column=self.sort.column, text=f"Sort: {titles[self.sort.column]}"))
        self.paint_sort_menu()

    def row_changed(self) -> None:
        row = self.current_view().currentIndex().row()
        self.selected = self.model.rows[row] if 0 <= row < len(self.model.rows) else None
        self.art_timer.start()

    # The rows in view, and a few more below them.
    def visible_ports(self) -> list[Port]:
        if self.view == "grid":
            start, end = self.grid.shown_rows(total=len(self.model.rows))

            return self.model.rows[start:end]

        first = self.table.rowAt(0)

        if first < 0:
            return []

        last = self.table.rowAt(self.table.viewport().height() - 1)
        last = len(self.model.rows) - 1 if last < 0 else last

        return self.model.rows[first : last + 1 + ART_LOOKAHEAD]

    # Every entry gets its art, like the Catalog tab: the chosen one first, then the rows on screen, then the
    # rows of the list, then the rest. Scrolling asks again, so the waiting order follows the eye.
    def ask_art(self) -> None:
        chosen = [self.selected] if self.selected else []
        ordered = chosen + self.visible_ports() + self.model.rows + self.ports
        # A dict keeps each entry at its first place, so the order above survives the duplicates.
        self.art.want(items=list({port.id: port for port in ordered}.values()))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.art_timer.start()

    def paint_status(self, job: PortSnapshot) -> None:
        if job.loading:
            self.spinner.start(text="Loading Switch Ports…")

            return

        self.spinner.stop()
        set_role(widget=self.status, role="error" if job.error else "muted")
        # The filter buttons already count each kind, so the line only speaks while narrowing the list.
        narrowed = bool(self.query.text().strip() or self.platforms)
        found = plural(count=len(self.model.rows), word="result") if narrowed else ""
        self.status.setText(job.error or found)

    def paint(self, job: PortSnapshot) -> None:
        if job.version != self.version:
            self.version = job.version
            self.ports = job.rows
            self.platforms &= {port.platform for port in self.ports}
            self.fill_platform_menu()
            self.paint_buttons()
            self.fit_columns()
            self.fill()

        self.refresh_button.setEnabled(not job.loading)
        self.paint_status(job=job)
        self.detail.show_port(port=self.selected, banner=self.picture(), needs_key=self.art.needs_key())

    # The banner of the chosen entry; an icon once it is known to have none, nothing while it is still looked up.
    def picture(self) -> QImage | None:
        if self.selected is None:
            return None

        banner = self.art.banner(item=self.selected)

        if banner is None and self.art.settled(item=self.selected):
            return self.art.placeholder(icon_name="cpu" if self.selected.kind == "emulator" else "gamepad")

        return banner

    def chosen(self) -> list[Port]:
        rows = sorted({index.row() for index in self.current_view().selectionModel().selectedIndexes()})

        return [self.model.rows[row] for row in rows if row < len(self.model.rows)]

    def open_page(self) -> None:
        if self.selected and self.selected.url:
            open_in_system(path=self.selected.url)

    def open_thread(self) -> None:
        if self.selected and self.selected.thread:
            open_in_system(path=self.selected.thread)

    def open_menu(self, point: QPoint) -> None:
        self.page_action.setEnabled(bool(self.selected and self.selected.url))
        self.thread_action.setEnabled(bool(self.selected and self.selected.thread))
        self.copy_action.setEnabled(bool(self.chosen()))
        menu = fill_menu(menu=QMenu(self), entries=(self.page_action, self.thread_action, None, self.copy_action))
        menu.exec(self.current_view().viewport().mapToGlobal(point))
        menu.deleteLater()

    def copy(self) -> None:
        links = [port.url for port in self.chosen() if port.url]

        if links:
            copy_text(text="\n".join(links))
