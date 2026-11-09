from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QTreeWidgetItem,
)


# Sorts by the column's key, with folders before other rows whichever way the column goes.
class SortItem(QTreeWidgetItem):
    def __init__(self, texts: List[str], name: str, size: int = 0, folder: bool = False, group: bool = False) -> None:
        super().__init__(texts)
        self.name = name.casefold()
        self.size = size
        self.folder = folder
        self.group = group
        # Column 1 holds the size, as __lt__ assumes; numbers line up on the right.
        self.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        tree = self.treeWidget()
        column = tree.sortColumn() if tree else 0
        ascending = not tree or tree.header().sortIndicatorOrder() == Qt.SortOrder.AscendingOrder

        if isinstance(other, SortItem) and self.folder != other.folder:
            return self.folder if ascending else other.folder

        if column == 0 or not isinstance(other, SortItem):
            return self.name < getattr(other, "name", "")

        if column == 1:
            return (self.size, self.name) < (other.size, other.name)

        return self.text(column) < other.text(column)
