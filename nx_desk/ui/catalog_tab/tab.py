import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import (
    QPoint,
    Qt,
)
from PySide6.QtGui import QAction, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...schemas.artwork import ArtFiles, ArtStamp
from ...schemas.github import UploadSnapshot
from ...schemas.presentation import DownloadChoice
from ...schemas.snapshot import ModRow, Snapshot
from ..cards.grid import CardGrid
from ..cards.thumbs import CoverThumbs
from ..icon_set import icon
from ..repo_picker import show_repo
from ..rows import SortState
from ..theme import LIST_COLUMNS, LIST_HIDE_BELOW, LIST_SORTABLE, SPACE, STATUS_FILTERS
from ..widgets.basics import (
    button,
    chooser,
    clear_on_escape,
    fill_menu,
    focus_box,
    label,
    menu_button,
    separator,
    tool,
)
from ..widgets.choice_popup import ChoicePopup
from ..widgets.click_label import ClickLabel
from ..widgets.log_pane import LogPane
from ..widgets.overlay import Overlay
from ..widgets.resize_watch import ResizeWatch
from ..widgets.spinner import Spinner
from ..widgets.view_switch import ViewSwitch
from .chip_delegate import ChipDelegate
from .filters import Filters
from .folders import Folders
from .game_model import ROW_HEIGHT, TAGS, GameModel
from .header import Header

if TYPE_CHECKING:
    from ..app import App

# The grid sorts by the columns the list lets a click sort.
SORTS = tuple((column.key, column.title) for column in LIST_COLUMNS if column.key in LIST_SORTABLE)


class CatalogTab(Filters, Header, Folders):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self.vault = app.vault
        self.items: Dict[str, ModRow] = {}
        self.shown_ids: Optional[List[str]] = None
        self.selected: Optional[str] = None
        self.picked: Set[str] = set()
        self.list_sort = SortState(column="game")
        self.chosen: List[str] = []
        self.missing: List[str] = []
        self.updates: List[str] = []
        self.redo_all: List[str] = []
        self.redo_chosen: List[str] = []
        self.download_choice: DownloadChoice = DownloadChoice(label="Download all", ids=[])
        self.redownload_choice: DownloadChoice = DownloadChoice(label="Re-download all", ids=[])
        self.detail_id: Optional[str] = None
        self.detail_key: Optional[Tuple[str, str]] = None
        self.art_id: Optional[str] = None
        self.art_image: Optional[QImage] = None
        # Banners by (catalog folder, game id); None when the files did not load.
        self.art_cache: Dict[Tuple[str, str], Optional[QImage]] = {}
        # Art files on disk, filled by the art threads; the UI thread turns them into banners.
        self.art_files: Dict[Tuple[str, str], ArtFiles] = {}
        self.art_signature: Optional[ArtStamp] = None
        self.genres: List[str] = []
        self.selected_genres: Set[str] = set()
        self.status_filter: Set[str] = set()
        self.downloading: Set[str] = set()
        self.reported_batch = 0
        self.catalog_text = ""
        self.active_catalog = self.vault.catalog.folder if self.vault.catalog else None
        self.shown_auto_repos: Optional[int] = None
        self.restoring = False
        self.mode = self.vault.catalog_view
        self.art_threads: List[threading.Thread] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addLayout(self.build_cards())
        layout.addLayout(self.build_toolbar())
        layout.addWidget(self.build_overall())
        layout.addWidget(self.build_body(), 1)
        self.set_mode(mode=self.mode)

    # Where mods come from and where they go.
    def build_cards(self) -> QHBoxLayout:
        cards = QHBoxLayout()
        cards.setSpacing(12)
        source = QGroupBox("Catalog")
        grid = QGridLayout(source)
        grid.setHorizontalSpacing(6)
        # Like the repository button: it names the catalog in use, and a click opens the list to change it or
        # to manage the catalogs.
        self.catalog_button = button(text="", action=self.app.open_manager, role="field")
        self.catalog_button.setMinimumWidth(190)
        chooser(widget=self.catalog_button, text="Add a catalog", tip="Choose or manage the catalogs")
        grid.addWidget(self.catalog_button, 0, 0)
        self.refresh_action = QAction(icon(name="refresh"), "Refresh catalog", self)
        self.refresh_action.setToolTip("Refresh the catalog")
        self.refresh_action.triggered.connect(lambda _=False: self.check())
        grid.addWidget(tool(action=self.refresh_action), 0, 1)
        grid.setColumnStretch(2, 1)
        grid.setRowStretch(1, 1)
        cards.addWidget(source)

        saving = QGroupBox("Saving")
        grid = QGridLayout(saving)
        grid.setHorizontalSpacing(6)
        grid.setColumnStretch(1, 1)
        grid.addWidget(label(text="Destination", role="muted"), 0, 0)
        # The folder and the mod name share one row: the folder takes what the name and the buttons leave.
        place = QHBoxLayout()
        place.setSpacing(6)
        self.download_entry = QLineEdit(self.vault.download_dir)
        self.download_entry.textChanged.connect(self.vault.set_download_dir)
        self.download_entry.textChanged.connect(self.download_entry.setToolTip)
        self.download_entry.setToolTip(self.vault.download_dir)
        self.download_entry.setPlaceholderText("Empty: the app's own downloaded folder")
        # A long path shows its start, which says where it is; the tooltip holds the whole path.
        self.download_entry.setCursorPosition(0)
        place.addWidget(self.download_entry, 1)
        self.download_button = button(text="Choose…", action=self.browse_download)
        self.move_button = button(text="Move", action=self.move_download)
        self.open_button = button(text="Open folder", action=self.open_folder)

        for widget in (self.download_button, self.move_button, self.open_button):
            place.addWidget(widget)

        place.addSpacing(SPACE["md"])
        place.addWidget(label(text="Mod name", role="muted"))
        self.mod_entry = QLineEdit(self.vault.mod_name)
        self.mod_entry.setFixedWidth(120)
        self.mod_entry.setPlaceholderText("e.g. VI")
        self.mod_entry.setToolTip("The name in every saved folder: <Game> - [<mod name>] - [<version>]")
        self.mod_entry.textChanged.connect(self.vault.set_mod_name)
        place.addWidget(self.mod_entry)
        grid.addLayout(place, 0, 1, 1, 4)
        grid.setRowStretch(2, 1)
        # Automatic uploads get their own row, so a narrow window does not squeeze them.
        grid.addWidget(label(text="After download", role="muted"), 1, 0)
        mod_row = QHBoxLayout()
        mod_row.setSpacing(SPACE["sm"])
        self.auto_upload_box = QCheckBox("Upload to GitHub")
        self.auto_upload_box.setChecked(self.vault.auto_upload)
        self.auto_upload_box.toggled.connect(self.auto_upload_changed)
        mod_row.addWidget(self.auto_upload_box)
        self.github_note = label(text="Add a GitHub token in Settings to use this", role="muted")
        self.github_note.hide()
        mod_row.addWidget(self.github_note)
        # The same repository popup as the GitHub tab, which lists owners too.
        self.auto_repo_button = button(text="", action=self.choose_auto_repo, role="field")
        show_repo(widget=self.auto_repo_button, repo=self.vault.auto_repo, repos=[])
        mod_row.addWidget(self.auto_repo_button)
        mod_row.addSpacing(8)
        self.auto_delete_box = QCheckBox("Delete local copy")
        self.auto_delete_box.setChecked(self.vault.auto_delete)
        self.auto_delete_box.toggled.connect(self.auto_delete_changed)
        mod_row.addWidget(self.auto_delete_box)
        mod_row.addStretch(1)
        grid.addLayout(mod_row, 1, 1, 1, 4)
        cards.addWidget(saving, 1)

        return cards

    def build_toolbar(self) -> QHBoxLayout:
        top = QHBoxLayout()
        top.setSpacing(6)
        # Two buttons, each also in the list's right-click menu. Each reads "... all" with no game or one game
        # picked, and "... selected" with several, which paint_chosen sets.
        self.download_action = QAction("Download all", self)
        self.download_action.triggered.connect(lambda _=False: self.get_download())
        self.redownload_action = QAction("Re-download all", self)
        self.redownload_action.triggered.connect(lambda _=False: self.get_redownload())
        self.get_button = tool(action=self.download_action, role="accent")
        self.redo_button = tool(action=self.redownload_action)
        self.update_all_button = button(text="", action=self.update_all, role="accent")
        self.stop_button = button(text="Stop all", action=self.stop_all, role="danger")

        for widget in (self.get_button, self.redo_button, self.update_all_button, self.stop_button):
            top.addWidget(widget)

        for widget in (self.update_all_button, self.stop_button):
            widget.hide()

        top.addStretch(1)

        return top

    # How the downloads are going: a row that shows only while something runs, and takes no room otherwise.
    def build_overall(self) -> QWidget:
        self.overall_row = QWidget()
        overall = QHBoxLayout(self.overall_row)
        overall.setContentsMargins(0, 0, 0, 0)
        overall.setSpacing(10)
        self.overall_label = label(text="", role="muted")
        self.overall_label.setFixedWidth(280)
        overall.addWidget(self.overall_label)
        self.overall_bar = QProgressBar()
        self.overall_bar.setRange(0, 1000)
        self.overall_bar.setTextVisible(False)
        overall.addWidget(self.overall_bar, 1)
        self.overall_row.hide()

        return self.overall_row

    # The list and the detail pane share a splitter, so the user picks how wide each one is.
    def build_body(self) -> QWidget:
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(SPACE["md"])
        self.model = GameModel(sort=self.list_sort)
        table = self.table = QTableView()
        table.setModel(self.model)
        table.setItemDelegateForColumn(TAGS, ChipDelegate(parent=table))
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, spec in enumerate(iterable=LIST_COLUMNS):
            width = spec.width

            if width:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
                header.resizeSection(index, width)

            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

        header.sectionClicked.connect(self.sort_list)
        thumbs = CoverThumbs(files=self.thumb_files, version=self.thumb_version, settled=self.thumb_settled)
        self.grid = CardGrid(model=self.model, thumbs=thumbs, changes=self.thumb_changes)
        self.list_empty = self.wire_view(view=table)
        self.grid_empty = self.wire_view(view=self.grid)
        table.setTextElideMode(Qt.TextElideMode.ElideRight)
        # The list, the grid and the log take turns in one place.
        self.body_stack = QStackedWidget()
        self.body_stack.addWidget(table)
        self.body_stack.addWidget(self.grid)
        self.log = LogPane()
        self.body_stack.addWidget(self.log)
        column = QWidget()
        # A shrinking window takes room from the detail pane first, so the list stays usable.
        column.setMinimumWidth(480)
        rows = QVBoxLayout(column)
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(SPACE["sm"])
        # The view tabs and the filters sit on the table, and what the catalog holds sits under it.
        rows.addLayout(self.build_header())
        rows.addWidget(self.body_stack, 1)
        rows.addLayout(self.build_footer())
        body.addWidget(column)
        body.addWidget(self.build_detail())
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 0)
        body.setSizes([1000, self.DETAIL_WIDTH])
        # The table's own size decides, whether the window or the splitter changed it.
        ResizeWatch(widget=table.viewport(), changed=self.fit_columns)

        return body

    # Above the table: the tabs of its views at the left, and what narrows or sorts it at the right.
    def build_header(self) -> QHBoxLayout:
        top = QHBoxLayout()
        top.setSpacing(6)
        self.view_switch = ViewSwitch(swap=self.show_view, bottom=0)
        top.addWidget(self.view_switch)
        top.addStretch(1)
        search_label = label(text="Search", role="muted")
        top.addWidget(search_label)
        self.search = QLineEdit()
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self.rebuild_rows)
        self.search.setPlaceholderText("Game, developer or genre")
        self.search.setToolTip("Ctrl+F to search, Esc to clear")
        self.search.setClearButtonEnabled(True)
        clear_on_escape(box=self.search)
        top.addWidget(self.search)
        self.genre_button = button(text="Genres")
        self.genre_popup = ChoicePopup(anchor=self.genre_button, idle_text="All genres")
        self.genre_popup.toggled.connect(self.toggle_genre)
        self.genre_popup.cleared.connect(self.clear_genres)
        self.genre_button.clicked.connect(self.genre_popup.open)
        top.addWidget(self.genre_button)
        self.status_button = button(text="Status")
        self.status_popup = ChoicePopup(anchor=self.status_button, idle_text="All statuses")
        self.status_popup.set_choices(
            choices=[(name, row.label) for name, row in STATUS_FILTERS.items()],
            picked=set(),
        )
        self.status_popup.toggled.connect(self.toggle_status)
        self.status_popup.cleared.connect(lambda: self.set_filter(names=set()))
        self.status_button.clicked.connect(self.status_popup.open)
        top.addWidget(self.status_button)
        # The grid has no column headers, so a menu sorts it by the same columns.
        self.sort_actions = {name: self.sort_action(name=name, title=title) for name, title in SORTS}
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
        # The grid has a menu to choose explicitly between List and Grid.
        rule = separator()
        top.addWidget(rule)
        self.mode_actions = {
            "list": self.mode_action(mode="list", title="List"),
            "grid": self.mode_action(mode="grid", title="Grid"),
        }
        self.mode_button = menu_button(
            text="",
            entries=self.mode_actions.values(),
            tip="Change view",
            glyph="menu",
        )
        self.mode_button.menu().aboutToShow.connect(self.paint_mode_menu)
        top.addWidget(self.mode_button)
        # Search and filters only shape the games, so the Log view hides them.
        self.list_only = [search_label, self.search, self.genre_button, self.status_button, rule, self.mode_button]

        return top

    # Under the table, at its left: how many games are downloaded, and the new ones and updates, which filter it.
    def build_footer(self) -> QHBoxLayout:
        notes = QHBoxLayout()
        notes.setSpacing(12)
        self.summary = label(text="", role="muted")
        self.summary_spinner = Spinner(target=self.summary)
        self.new_label = ClickLabel(text="", role="new")
        self.update_label = ClickLabel(text="", role="update")
        self.new_label.clicked.connect(lambda: self.toggle_filter(name="new"))
        self.update_label.clicked.connect(lambda: self.toggle_filter(name="update"))

        for widget in (self.summary, self.new_label, self.update_label):
            notes.addWidget(widget)

        notes.addStretch(1)

        return notes

    # What the list and the grid do alike: the chosen rows, opening, the menu and the empty message.
    def wire_view(self, view: QAbstractItemView) -> QLabel:
        view.selectionModel().selectionChanged.connect(self.selection_changed)
        view.selectionModel().currentRowChanged.connect(self.selection_changed)
        view.doubleClicked.connect(lambda _: self.act())
        enter = QShortcut(QKeySequence(Qt.Key.Key_Return), view)
        enter.setContext(Qt.ShortcutContext.WidgetShortcut)
        enter.activated.connect(lambda: self.get_chosen() if len(self.picked) > 1 else self.act())
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self.open_menu)
        note = label(text="", role="muted", parent=view.viewport())
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.hide()
        Overlay(viewport=view.viewport(), message=note)

        return note

    def sort_action(self, name: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.choose_sort(name=name))

        return action

    def sort_direction_action(self, ascending: bool, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_sort_direction(ascending=ascending))

        return action

    def paint_sort_menu(self) -> None:
        for name, action in self.sort_actions.items():
            action.setChecked(name == self.list_sort.column)

        for ascending, action in self.sort_direction_actions.items():
            action.setChecked(ascending == self.list_sort.ascending)

    def choose_sort(self, name: str) -> None:
        self.list_sort.choose(column=name)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(LIST_COLUMNS) - 1)
        self.rebuild_rows()
        self.paint_sort_menu()

    def set_sort_direction(self, ascending: bool) -> None:
        self.list_sort.set_direction(ascending=ascending)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(LIST_COLUMNS) - 1)
        self.rebuild_rows()
        self.paint_sort_menu()

    def mode_action(self, mode: str, title: str) -> QAction:
        action = QAction(title, self)
        action.setCheckable(True)
        action.triggered.connect(lambda _=False: self.set_mode(mode=mode))

        return action

    def paint_mode_menu(self) -> None:
        for mode, action in self.mode_actions.items():
            action.setChecked(mode == self.mode)

    def open_menu(self, point: QPoint) -> None:
        self.paint_chosen()
        menu = fill_menu(menu=QMenu(self), entries=(self.download_action, self.redownload_action))
        menu.exec(self.current_view().viewport().mapToGlobal(point))
        menu.deleteLater()

    # Columns the detail pane also shows go first when the list gets narrow, so it never scrolls sideways.
    def fit_columns(self) -> None:
        width = self.table.viewport().width()

        for index, spec in enumerate(iterable=LIST_COLUMNS):
            name = spec.key
            limit = LIST_HIDE_BELOW.get(name)
            self.table.setColumnHidden(index, limit is not None and width < limit)

    def build_detail(self) -> QStackedWidget:
        self.detail = QStackedWidget()
        # The banner scales with the pane, so it can be dragged much wider than its base size.
        self.detail.setMinimumWidth(self.ART_SIZE[0] + SPACE["sm"])
        self.detail.setMaximumWidth(900)
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.art = label()
        self.art.hide()
        column.addWidget(self.art)
        self.name = label(text="", role="name")
        self.name.setWordWrap(True)
        column.addWidget(self.name)
        self.state_label = label(text="", role="strong")
        self.state_label.setWordWrap(True)
        column.addWidget(self.state_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()
        column.addWidget(self.progress)
        self.action = button(text="", action=self.act)
        column.addWidget(self.action)
        # The description grows to its text and the whole pane scrolls, so there is one scroll bar.
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        column.addWidget(self.text)
        column.addStretch(1)
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.detail_scroll.setWidget(page)
        ResizeWatch(widget=self.detail_scroll.viewport(), changed=self.fit_detail)
        self.detail.addWidget(self.detail_scroll)
        empty = label(text="No mod selected", role="muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.addWidget(empty)
        self.detail.setCurrentIndex(1)

        return self.detail

    # Ctrl+F: the search shapes the games, so they come back first.
    def focus_search(self) -> None:
        self.view_switch.show_view(view="list")
        focus_box(box=self.search)

    # The games as a list or as a grid; the choice is remembered, and the first tab names it.
    def set_mode(self, mode: str) -> None:
        self.mode = mode

        if mode != self.vault.catalog_view:
            self.vault.set_catalog_view(view=mode)

        self.view_switch.rename(view="list", text=mode.capitalize())
        self.paint_mode_menu()
        self.view_switch.show_view(view="list")

    # "list" is the games, in the mode chosen; "log" replaces them for a while.
    def show_view(self, view: str) -> None:
        logging = view == "log"
        self.body_stack.setCurrentIndex(2 if logging else 1 if self.mode == "grid" else 0)
        # The detail pane describes a game, so the log takes its room.
        self.detail.setVisible(not logging)

        for widget in self.list_only:
            widget.setVisible(not logging)

        self.sort_button.setVisible(not logging and self.mode == "grid")

        if logging:
            self.log.show_latest()

            return

        # The other view was hidden while the rows changed, so the chosen rows are chosen there again.
        self.restore_selection()
        self.current_view().setFocus()

    def refresh(self, snapshot: Snapshot, github: UploadSnapshot) -> None:
        if snapshot.active != self.active_catalog:
            self.active_catalog = snapshot.active
            self.reset_filters()

        self.items = {item.id: item for item in snapshot.items}
        genres = sorted({tag for item in self.items.values() for tag in item.tags}, key=str.lower)

        if genres != self.genres:
            self.genres = genres
            self.selected_genres &= set(genres)
            self.fill_genre_menu()
            self.shown_ids = None

        self.paint_catalogs(snapshot=snapshot)
        self.rebuild_rows()
        self.follow_downloads()
        self.preload_art()
        self.show_detail()
        self.paint_header(snapshot=snapshot)
        self.log.paint(lines=snapshot.log)
        self.paint_overall(batch=snapshot.batch, checking=snapshot.checking)
        self.paint_auto_upload(github=github)
        busy = self.vault.busy()

        for widget in (self.download_entry, self.download_button, self.move_button):
            widget.setEnabled(not busy)
