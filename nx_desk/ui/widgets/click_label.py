from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QLabel,
)

from ..style import set_role


class ClickLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = "", role: Optional[str] = None) -> None:
        super().__init__(text)

        if role:
            set_role(widget=self, role=role)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mousePressEvent(event)
