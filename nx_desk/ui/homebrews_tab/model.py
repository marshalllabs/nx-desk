from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt

from ...schemas.card import Card
from ...schemas.homebrew import Homebrew
from ..cards.layout import CARD_ROLE
from ..rows import SortState

COLUMNS = (
    ("name", "Name", 0),
    ("groups", "Group", 140),
    ("category", "Type", 140),
    ("version", "Version", 100),
    ("authors", "Authors", 150),
    ("updated", "Updated", 110),
)


def cell(row: Homebrew, column: str) -> str:
    return {
        "name": row.name,
        "groups": ", ".join(row.groups),
        "category": row.category,
        "version": row.version,
        "authors": row.authors,
        "updated": row.updated,
    }.get(column, "")


class HomebrewModel(QAbstractTableModel):
    def __init__(self, order: SortState) -> None:
        super().__init__()
        self.order = order
        self.rows: list[Homebrew] = []

    def set_rows(self, rows: list[Homebrew]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None

        row = self.rows[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return cell(row=row, column=COLUMNS[index.column()][0])

        if role == CARD_ROLE:
            return Card(key=row.id, title=row.name, subtitle=row.category or ", ".join(row.groups), icon="cpu")

        if role == Qt.ItemDataRole.ToolTipRole:
            return row.description or row.name

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            name, title, _ = COLUMNS[section]

            return self.order.title(column=name, text=title)

        return None
