from PySide6.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from ..theme import COLORS


# Genres show as chips on one line; those that do not fit become a "+N" chip.
class ChipDelegate(QStyledItemDelegate):
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        style = QStyleOptionViewItem(option)
        self.initStyleOption(style, index)
        style.text = ""
        widget = option.widget
        (widget.style() if widget else QApplication.style()).drawControl(
            QStyle.ControlElement.CE_ItemViewItem,
            style,
            painter,
            widget,
        )
        tags = index.data(Qt.ItemDataRole.UserRole) or ()
        font = QFont(option.font)
        font.setPointSize(9)
        metrics = QFontMetrics(font)
        painter.save()
        painter.setFont(font)
        height = metrics.height() + 4
        top = option.rect.top() + (option.rect.height() - height) // 2
        x = option.rect.left() + 8
        right = option.rect.right() - 8

        for number, tag in enumerate(tags):
            width = metrics.horizontalAdvance(tag) + 12
            rest = len(tags) - number
            more = metrics.horizontalAdvance(f"+{rest}") + 12

            if x + width > right - (more + 4 if rest > 1 else 0):
                self.chip(painter=painter, rect=QRect(x, top, more, height), text=f"+{rest}")
                break

            self.chip(painter=painter, rect=QRect(x, top, width, height), text=tag)
            x += width + 4

        painter.restore()

    @staticmethod
    def chip(painter: QPainter, rect: QRect, text: str) -> None:
        painter.fillRect(rect, QColor(COLORS["panel"]))
        painter.setPen(QColor(COLORS["ink"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
