from typing import Collection, Iterable, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .basics import button, label


# Boxes to tick under a button. Unlike a menu it scrolls once it is taller than the room on the
# screen, and it stays open while several boxes are ticked.
class ChoicePopup(QFrame):
    toggled = Signal(str, bool)
    cleared = Signal()
    SCREEN_SHARE = 0.6
    ROW = 28
    # The left and right padding style.py gives each row.
    ROW_PADDING = 12
    # The check box and the gap after it.
    CHECK = 38
    # Longer lists get a box to narrow them down.
    FILTER_FROM = 10

    def __init__(self, anchor: QWidget, idle_text: str) -> None:
        super().__init__(anchor, Qt.WindowType.Popup)
        self.anchor = anchor
        self.idle_text = idle_text
        self.setObjectName("choices")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        head = self.head = QHBoxLayout()
        self.count = label(text="", role="muted")
        head.addWidget(self.count, 1)
        self.clear_button = button(text="Clear", action=self.cleared.emit)
        head.addWidget(self.clear_button)
        layout.addLayout(head)
        self.query = QLineEdit()
        self.query.setPlaceholderText("Filter")
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(self.narrow)
        layout.addWidget(self.query)
        self.choices = QListWidget()
        self.choices.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.choices.setUniformItemSizes(True)
        self.choices.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.choices.itemChanged.connect(self.changed)
        self.choices.itemClicked.connect(self.flip)
        layout.addWidget(self.choices)
        self.empty = label(text="No match", role="muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.hide()
        layout.addWidget(self.empty)

    def changed(self, item: QListWidgetItem) -> None:
        self.paint_count()
        self.toggled.emit(item.data(Qt.ItemDataRole.UserRole), self.is_checked(item=item))

    def paint_count(self) -> None:
        picked = sum(self.is_checked(item=self.choices.item(index)) for index in range(self.choices.count()))
        self.count.setText(f"{picked} selected" if picked else self.idle_text)
        self.clear_button.setEnabled(bool(picked))

    def narrow(self, text: str) -> None:
        text = text.strip().casefold()
        shown = 0

        for index in range(self.choices.count()):
            item = self.choices.item(index)
            item.setHidden(bool(text) and text not in item.text().casefold())
            shown += not item.isHidden()

        self.choices.setVisible(bool(shown))
        self.empty.setVisible(not shown)

    @staticmethod
    def is_checked(item: QListWidgetItem) -> bool:
        return item.checkState() == Qt.CheckState.Checked

    # The row is not user-checkable, so a click anywhere on it, box included, flips it exactly once.
    def flip(self, item: QListWidgetItem) -> None:
        state = Qt.CheckState.Unchecked if self.is_checked(item=item) else Qt.CheckState.Checked
        item.setCheckState(state)

    # Each choice is a (key, text) pair; signals carry the key.
    def set_choices(self, choices: Iterable[Tuple[str, str]], picked: Collection[str]) -> None:
        self.choices.blockSignals(True)
        self.choices.clear()

        for key, text in choices:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setSizeHint(QSize(0, self.ROW))
            item.setCheckState(Qt.CheckState.Checked if key in picked else Qt.CheckState.Unchecked)
            self.choices.addItem(item)

        self.choices.blockSignals(False)
        self.paint_count()

    def open(self) -> None:
        screen = self.anchor.screen().availableGeometry()
        self.query.clear()
        self.query.setVisible(self.choices.count() >= self.FILTER_FROM)
        # Rows have a fixed height, so the list is exactly as tall as its rows until it needs to scroll.
        frame = 2 * self.choices.frameWidth()
        tallest = int(screen.height() * self.SCREEN_SHARE)
        height = min(max(1, self.choices.count()) * self.ROW + frame, tallest)
        # As wide as the longest row, plus the item padding and the scroll bar when the list scrolls.
        scroll = self.choices.verticalScrollBar().sizeHint().width() if height == tallest else 0
        metrics = self.choices.fontMetrics()
        texts = [self.choices.item(index).text() for index in range(self.choices.count())]
        longest = max((metrics.horizontalAdvance(text) for text in texts), default=0)
        width = longest + self.CHECK + self.ROW_PADDING + frame + scroll
        # A list hints 256 px on its own, so its width is fixed; only the header may make it wider.
        self.choices.setFixedSize(max(width, self.head.sizeHint().width()), height)
        self.empty.setFixedHeight(height)
        self.adjustSize()
        below = self.anchor.mapToGlobal(self.anchor.rect().bottomLeft())
        x = min(max(screen.left(), below.x()), screen.right() - self.width())
        y = below.y() + 4

        if y + self.height() > screen.bottom():
            y = max(screen.top(), self.anchor.mapToGlobal(self.anchor.rect().topLeft()).y() - self.height() - 4)

        self.move(x, y)
        self.show()
