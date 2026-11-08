from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QTreeWidgetItemIterator,
)

from ...schemas.common import LogEntry
from ..theme import COLORS
from .basics import copy_text
from .overlay import Overlay


def paint_item(
    item: QTreeWidgetItem,
    columns: int,
    foreground: str | None = None,
    background: str | None = None,
    only: int | None = None,
) -> None:
    # With only, the colour goes to that one column, such as the status, and the rest stays plain.
    for column in range(columns):
        colored = foreground and (only is None or column == only)
        item.setForeground(column, QBrush(QColor(foreground)) if colored else QBrush())
        item.setBackground(column, QBrush(QColor(background)) if background else QBrush())


# Lines of one game go under a row named after it, which also shows the game's latest step.
class LogPane(QTreeWidget):
    LEVELS = {"info": "muted", "ok": "ok", "warn": "accent", "error": "bad"}

    def __init__(self) -> None:
        super().__init__()
        self.count = 0
        self.groups: dict[str, QTreeWidgetItem] = {}
        self.setColumnCount(3)
        self.setHeaderLabels(["Game / step", "Latest step", "Time"])
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.setUniformRowHeights(True)
        header = self.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(2, 90)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        # Shown until the first line arrives, so an empty log does not look broken.
        self.empty = QLabel("No activity yet. Downloads, uploads and checks show up here.", self.viewport())
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setProperty("role", "muted")
        Overlay(viewport=self.viewport(), message=self.empty)
        self.bold = self.bold_font()
        copy = QAction(self)
        copy.setShortcut(QKeySequence.StandardKey.Copy)
        copy.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        copy.triggered.connect(self.copy)
        self.addAction(copy)
        select = QAction(self)
        select.setShortcut(QKeySequence.StandardKey.SelectAll)
        select.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        select.triggered.connect(self.select_everything)
        self.addAction(select)

    def bold_font(self) -> QFont:
        bold = QFont(self.font())
        bold.setBold(True)

        return bold

    # A font picked in Settings reaches the group rows too, which hold their own bold copy.
    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)

        if event.type() == QEvent.Type.FontChange:
            self.bold = self.bold_font()

            for group in self.groups.values():
                for column in range(3):
                    group.setFont(column, self.bold)

    def paint(self, lines: list[LogEntry]) -> None:
        self.empty.setVisible(not lines)

        if len(lines) == self.count:
            return

        if len(lines) < self.count:
            self.clear()
            self.groups = {}
            self.count = 0

        bar = self.verticalScrollBar()
        following = bar.value() >= bar.maximum()

        for level, time, game, text in lines[self.count :]:
            level = level if level in self.LEVELS else "info"
            color = QColor(COLORS[self.LEVELS[level]])
            line = QTreeWidgetItem([text, "", time])
            line.setForeground(0, color)

            if not game:
                self.addTopLevelItem(line)
                continue

            group = self.groups.get(game)
            opened = False

            if group is None:
                group = self.groups[game] = QTreeWidgetItem([game, "", ""])

                for column in range(3):
                    group.setFont(column, self.bold)
            else:
                # The game that moved last goes to the bottom, so the end is the newest line.
                opened = group.isExpanded()
                self.takeTopLevelItem(self.indexOfTopLevelItem(group))

            group.addChild(line)
            group.setText(1, text)
            group.setText(2, time)
            ink = QColor(COLORS["ink" if level == "info" else self.LEVELS[level]])

            for column in range(3):
                group.setForeground(column, ink)

            self.addTopLevelItem(group)
            group.setExpanded(opened)

        self.count = len(lines)

        if following:
            self.show_latest()

    def show_latest(self) -> None:
        QTimer.singleShot(0, self.scrollToBottom)

    # Lines under closed games count too, which a tree's own select all leaves out.
    def select_everything(self) -> None:
        walker = QTreeWidgetItemIterator(self)

        while walker.value():
            walker.value().setSelected(True)
            walker += 1

    def copy(self) -> None:
        found: list[str] = []
        walker = QTreeWidgetItemIterator(self)

        while walker.value():
            item = walker.value()

            if item.isSelected():
                found.append(f"{item.text(2)}  {item.text(0)}".strip())

            walker += 1

        if found:
            copy_text(text="\n".join(found))
