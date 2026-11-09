from typing import Dict, Final, List, Union

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtGui import QColor

from ...config import MISSING_VERSION
from ...names import clean_game_name, display_version
from ...schemas.card import Card
from ...schemas.presentation import GameCells
from ...schemas.snapshot import ModRow
from ...utils.sizes import format_size
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
class GameModel(QAbstractTableModel):
    def __init__(self, sort: SortState) -> None:
        super().__init__()
        self.order = sort
        self.ids: List[str] = []
        self.cells: Dict[str, GameCells] = {}

    @staticmethod
    def cells_of(item: ModRow) -> GameCells:
        versions = version_cells(item=item)
        mod_version = versions.mod
        game_version = versions.game
        missing = display_version(game_version=item.game_version) == MISSING_VERSION

        return GameCells(
            name=clean_game_name(name=item.name),
            tags=tuple(item.tags),
            mod_version=mod_version,
            game_version=game_version,
            size=format_size(value=item.size),
            status=status_text(item=item),
            tone=row_tag(item=item),
            missing=missing,
            progress=progress_of(item=item),
        )

    # A new set or order of rows resets the model; otherwise only changed rows repaint.
    def set_rows(self, ids: List[str], items: Dict[str, ModRow]) -> bool:
        if ids != self.ids:
            self.beginResetModel()
            self.ids = list(ids)
            self.cells = {entry_id: self.cells_of(item=items[entry_id]) for entry_id in ids}
            self.endResetModel()

            return True

        for row, entry_id in enumerate(iterable=ids):
            cells = self.cells_of(item=items[entry_id])

            if cells != self.cells.get(entry_id):
                self.cells[entry_id] = cells
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(LIST_COLUMNS) - 1))

        return False

    def rowCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.ids)

    def columnCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(LIST_COLUMNS)

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = Qt.ItemDataRole.DisplayRole) -> object:
        cells = self.cells[self.ids[index.row()]]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            values = [
                cells.name,
                ", ".join(cells.tags),
                cells.mod_version,
                cells.game_version,
                cells.size,
                cells.status,
            ]

            return values[column]

        if role == Qt.ItemDataRole.UserRole:
            return cells.tags

        if role == CARD_ROLE:
            return Card(
                key=self.ids[index.row()],
                title=cells.name,
                subtitle=cells.status,
                tone=ROW_COLORS[cells.tone],
                progress=cells.progress,
            )

        if role == Qt.ItemDataRole.ForegroundRole:
            if column == GAME_VERSION and cells.missing:
                return QColor(COLORS["miss"])

            # Only the status carries its colour, next to its words; the rest stays plain to read.
            return QColor(COLORS[ROW_COLORS[cells.tone]] if column == STATUS else COLORS["ink"])

        # Sizes line up on the right, like the totals in the confirm dialogs.
        if role == Qt.ItemDataRole.TextAlignmentRole and column == SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        if role == Qt.ItemDataRole.ToolTipRole and column == 0:
            return cells.name

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            column = LIST_COLUMNS[section]
            name, title = column.key, column.title

            return self.order.title(column=name, text=title)

        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole and section == SIZE:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return None
