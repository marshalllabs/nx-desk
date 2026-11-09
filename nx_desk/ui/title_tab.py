import functools
import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QAction, QFont, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..catalog.title_ids import find_titles
from ..schemas.presentation import Column
from ..schemas.title import TitleRow, TitleSnapshot
from ..utils.text import plural
from .rows import SortState
from .style import set_role
from .widgets.basics import button, clear_on_escape, copy_text, focus_box, label
from .widgets.spinner import Spinner

if TYPE_CHECKING:
    from .app import App

SECTIONS = (("", "All"), ("games", "Games"), ("system", "System"), ("sysmodules", "Sysmodules"))
SECTION_TYPES = {"games": "Game", "system": "System", "sysmodules": "Sysmodule"}
# Name is wide but resizable; the last column takes what is left, so Type and Group sit beside the name.
COLUMNS: Tuple[Column, ...] = (
    Column(key="id", title="Title ID", width=190),
    Column(key="name", title="Name", width=620),
    Column(key="kind", title="Type", width=120),
    Column(key="detail", title="Group", width=0),
)


def mono_font() -> QFont:
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(QApplication.font().pointSize())

    return font


# A title row with its type spelled out for the Type column.
class ShownTitle(TitleRow):
    kind: str


def cell(row: ShownTitle, column: str) -> str:
    return {"id": row.id, "name": row.name, "kind": row.kind, "detail": row.detail}[column]


# A model draws only the rows in view, so the whole list shows at once.
class TitleModel(QAbstractTableModel):
    def __init__(self, sort: SortState) -> None:
        super().__init__()
        self.order = sort
        self.rows: List[ShownTitle] = []

    def set_rows(self, rows: List[ShownTitle]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if role == Qt.ItemDataRole.DisplayRole:
            return cell(row=self.rows[index.row()], column=COLUMNS[index.column()].key)

        # Title IDs are 16 hex digits; a fixed-width font keeps them aligned and easy to compare.
        if role == Qt.ItemDataRole.FontRole and index.column() == 0:
            return mono_font()

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            column = COLUMNS[section]
            name, title = column.key, column.title

            return self.order.title(column=name, text=title)

        return None


class TitleTab(QWidget):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self.vault = app.vault
        self.version: Optional[int] = None
        self.rows: List[ShownTitle] = []
        self.section = ""
        self.sort = SortState(column="name")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(label(text="Search", role="muted"))
        self.query = QLineEdit()
        self.query.setFixedWidth(320)
        self.query.textChanged.connect(self.fill)
        self.query.setPlaceholderText("Title ID or name")
        self.query.setToolTip("Ctrl+F to search, Esc to clear")
        self.query.setClearButtonEnabled(True)
        clear_on_escape(box=self.query)
        top.addWidget(self.query)
        top.addSpacing(10)
        self.buttons: Dict[str, QPushButton] = {}

        for section, _ in SECTIONS:
            choice = button(text="", action=functools.partial(self.choose, section))

            choice.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            top.addWidget(choice)
            self.buttons[section] = choice

        top.addStretch(1)
        self.refresh_button = button(text="Refresh", action=lambda: self.load(force=True))
        top.addWidget(self.refresh_button)
        layout.addLayout(top)
        self.status = label(text="", role="muted")
        self.spinner = Spinner(target=self.status)
        layout.addWidget(self.status)
        self.model = TitleModel(sort=self.sort)
        table = self.table = QTableView()
        table.setModel(self.model)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(30)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, spec in enumerate(iterable=COLUMNS):
            width = spec.width

            if width:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(index, width)

            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

        header.sectionClicked.connect(self.sort_by)
        copy = QAction(table)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy.triggered.connect(self.copy)
        table.addAction(copy)
        layout.addWidget(table, 1)
        self.paint_buttons()

    def focus_search(self) -> None:
        focus_box(box=self.query)

    def load(self, force: bool = False) -> None:
        threading.Thread(target=self.vault.load_title_ids, args=(force,), daemon=True).start()

    def choose(self, section: str) -> None:
        self.section = section
        self.paint_buttons()
        self.fill()

    def paint_buttons(self) -> None:
        for section, text in SECTIONS:
            count = sum(row.section == section or not section for row in self.rows)
            self.buttons[section].setText(f"{text} ({count:,})")
            # A filter, not an action: the same quiet segmented look as the List and Log pair.
            chosen = section == self.section
            set_role(widget=self.buttons[section], role="segment-on" if chosen else "segment")
            self.buttons[section].setAccessibleName(f"{text} ({count:,})" + (", shown" if chosen else ""))

    def sort_by(self, column: int) -> None:
        self.sort.toggle(column=COLUMNS[column].key)
        self.fill()

    def fill(self) -> None:
        rows = [row for row in self.rows if not self.section or row.section == self.section]
        found = find_titles(rows=rows, query=self.query.text().strip())
        found = sorted(
            found,
            key=lambda row: cell(row=row, column=self.sort.column).casefold(),
            reverse=not self.sort.ascending,
        )
        self.model.set_rows(rows=found)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(COLUMNS) - 1)
        self.table.scrollToTop()
        self.paint_status(job=self.vault.title_snapshot())

    def paint_status(self, job: TitleSnapshot) -> None:
        if job.loading:
            self.spinner.start(text="Loading title IDs…")

            return

        self.spinner.stop()
        set_role(widget=self.status, role="error" if job.error else "muted")
        # The filter buttons already count each section, so the line only speaks while searching.
        query = self.query.text().strip()
        found = f"{plural(count=len(self.model.rows), word='title')} match “{query}”" if query else ""
        self.status.setText(job.error or found)

    def paint(self, job: TitleSnapshot) -> None:
        if job.version != self.version:
            self.version = job.version
            self.rows = [ShownTitle(**dict(row), kind=SECTION_TYPES[row.section]) for row in job.rows]
            self.paint_buttons()
            self.fill()

        self.refresh_button.setEnabled(not job.loading)
        self.paint_status(job=job)

    def copy(self) -> None:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})

        if rows:
            copy_text(text="\n".join(self.model.rows[row].id for row in rows))
