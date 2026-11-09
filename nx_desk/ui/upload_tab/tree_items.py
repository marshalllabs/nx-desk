from typing import Iterator, List, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

ROW_COLORS = {
    "downloaded": ("ok", "ok_soft"),
    "fresh": ("ok", "ok_soft"),
    "uploaded": ("ok", None),
    "missing": ("muted", None),
    "invalid": ("bad", None),
    "working": ("accent", None),
    "done": ("ok", None),
    "error": ("bad", None),
    "local": ("ok", None),
    "orphan": ("miss", None),
    "same": ("ok", None),
    "differs": ("accent", None),
    "only": ("miss", None),
}


def items_of(tree: QTreeWidget) -> Iterator[QTreeWidgetItem]:
    walker = QTreeWidgetItemIterator(tree)

    while walker.value():
        yield walker.value()
        walker += 1


def children(item: QTreeWidgetItem) -> List[QTreeWidgetItem]:
    return [child for index in range(item.childCount()) if (child := item.child(index))]


def make_tree(titles: Sequence[str]) -> QTreeWidget:
    tree = QTreeWidget()
    tree.setColumnCount(len(titles))
    tree.setHeaderLabels(list(titles))
    tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    tree.setUniformRowHeights(True)
    # File names end in the version, so a long one loses its middle rather than its end.
    tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
    tree.setSortingEnabled(True)
    tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    header = tree.header()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    for column in range(1, len(titles)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(column, 110)

    # The status column only needs room for "Not downloaded" or a progress text; the name gets the rest.
    header.resizeSection(len(titles) - 1, 150)
    tree.headerItem().setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    return tree


# A row shows when its name holds every word, or a row above or below it does, so a game row keeps
# its folders and a folder keeps the path to it. Hidden rows lose their selection, so no action
# reaches what cannot be seen.
def filter_tree(tree: QTreeWidget, text: str) -> None:
    words = text.casefold().split()

    def visit(item: QTreeWidgetItem, inherited: bool) -> bool:
        own = all(word in item.text(0).casefold() for word in words)
        below = False

        for child in children(item=item):
            below = visit(item=child, inherited=inherited or own) or below

        shown = not words or own or inherited or below
        item.setHidden(not shown)

        if not shown:
            item.setSelected(False)

        elif words and below:
            item.setExpanded(True)

        return shown

    for index in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(index)

        if top is not None:
            visit(item=top, inherited=False)
