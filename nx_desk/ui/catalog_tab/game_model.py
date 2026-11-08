from typing import Final

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QColor

from ...config import MISSING_VERSION
from ...names import clean_game_name, display_version, format_size
from ...schemas.card import Card
from ...schemas.snapshot import ModRow
from ..cards.layout import CARD_ROLE
from ..rows import SortState, progress_of, row_tag, status_text, version_cells
from ..theme import COLORS, LIST_COLUMNS, ROW_COLORS

TAGS: Final = 1

GAME_VERSION: Final = 3

SIZE: Final = 4

STATUS: Final = 5

ROW_HEIGHT = 36

# What a row shows: game, genres, mod version, game version, size, status, row color, whether the game
# version is missing and how far a transfer has come (negative while none runs).
Cells = tuple[str, tuple[str, ...], str, str, str, str, str, bool, float]


class GameModel(QAbstractTableModel):
    def __init__(self, sort: SortState) -> None:
        super().__init__()
        self.order = sort
        self.ids: list[str] = []
        self.cells: dict[str, Cells] = {}

    @staticmethod
    def cells_of(item: ModRow) -> Cells:
        mod_version, game_version = version_cells(item=item)
        missing = display_version(game_version=item.game_version) == MISSING_VERSION

        return (
            clean_game_name(name=item.name),
            tuple(item.tags),
            mod_version,
            game_version,
            format_size(value=item.size),
            status_text(item=item),
            row_tag(item=item),
            missing,
            progress_of(item=item),
        )

    # A new set or order of rows resets the model; otherwise only changed rows repaint.
    def set_rows(self, ids: list[str], items: dict[str, ModRow]) -> bool:
        if ids != self.ids:
            self.beginResetModel()
            self.ids = list(ids)
            self.cells = {entry_id: self.cells_of(item=items[entry_id]) for entry_id in ids}
            self.endResetModel()

            return True

        for row, entry_id in enumerate(ids):
            cells = self.cells_of(item=items[entry_id])

            if cells != self.cells.get(entry_id):
                self.cells[entry_id] = cells
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(LIST_COLUMNS) - 1))

        return False

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.ids)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(LIST_COLUMNS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        cells = self.cells[self.ids[index.row()]]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return ", ".join(cells[TAGS]) if column == TAGS else cells[column]

        if role == Qt.ItemDataRole.UserRole:
            return cells[TAGS]

        if role == CARD_ROLE:
            return Card(
                key=self.ids[index.row()],
                title=cells[0],
                subtitle=cells[STATUS],
                tone=ROW_COLORS[cells[6]],
                progress=cells[8],
            )

        if role == Qt.ItemDataRole.ForegroundRole:
            if column == GAME_VERSION and cells[7]:
                return QColor(COLORS["miss"])

            # Only the status carries its colour, next to its words; the rest stays plain to read.
            return QColor(COLORS[ROW_COLORS[cells[6]]] if column == STATUS else COLORS["ink"])

        # Sizes line up on the right, like the totals in the confirm dialogs.
        if role == Qt.ItemDataRole.TextAlignmentRole and column == SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ToolTipRole and column == 0:
            return cells[0]

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            name, title, _ = LIST_COLUMNS[section]

            return self.order.title(column=name, text=title)

        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole and section == SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return None
