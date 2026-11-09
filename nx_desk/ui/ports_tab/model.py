from typing import Final, List, Tuple, Union

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor

from ...catalog.ports import status_label, status_tone
from ...schemas.card import Card
from ...schemas.port import Port
from ...schemas.presentation import Column
from ..cards.layout import CARD_ROLE
from ..rows import SortState
from ..theme import COLORS

COLUMNS: Tuple[Column, ...] = (
    Column(key="name", title="Name", width=0),
    Column(key="platform", title="Platform", width=230),
    Column(key="type", title="Type", width=150),
    Column(key="version", title="Version", width=130),
    Column(key="updated", title="Updated", width=110),
    Column(key="status", title="Status", width=170),
)
STATUS: Final = 5
ROW_HEIGHT = 36
# Columns a narrow list hides first, with the table width below which each one goes. The detail
# pane shows the same values, so nothing is lost.
HIDE_BELOW = {"type": 820, "updated": 700, "version": 600}


def type_text(port: Port) -> str:
    text = "Emulator" if port.kind == "emulator" else "Port"

    return f"{text} · {port.emulates}" if port.emulates else text


def cell(port: Port, column: str) -> str:
    match column:
        case "name":
            return port.name
        case "platform":
            return port.platform
        case "type":
            return type_text(port=port)
        case "version":
            return port.version or "-"
        case "updated":
            return port.updated or "-"
        case _:
            return status_label(status=port.status) or "-"


class PortModel(QAbstractTableModel):
    def __init__(self, sort: SortState) -> None:
        super().__init__()
        self.order = sort
        self.rows: List[Port] = []

    def set_rows(self, rows: List[Port]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent: Union[QModelIndex, QPersistentModelIndex] = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def data(self, index: Union[QModelIndex, QPersistentModelIndex], role: int = Qt.ItemDataRole.DisplayRole) -> object:
        port = self.rows[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return cell(port=port, column=COLUMNS[column].key)

        if role == Qt.ItemDataRole.ForegroundRole:
            # Only the status carries its colour, next to its words; the rest stays plain to read.
            return QColor(COLORS[status_tone(status=port.status) if column == STATUS else "ink"])

        if role == CARD_ROLE:
            icon = "cpu" if port.kind == "emulator" else "gamepad"

            return Card(key=port.id, title=port.name, subtitle=port.platform, icon=icon)

        if role == Qt.ItemDataRole.ToolTipRole and column == 0:
            return f"{port.name}\n{port.id}"

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            column = COLUMNS[section]
            name, title = column.key, column.title

            return self.order.title(column=name, text=title)

        return None
