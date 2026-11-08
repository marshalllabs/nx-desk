from PySide6.QtCore import (
    QEvent,
    QObject,
)
from PySide6.QtWidgets import (
    QWidget,
)


# An empty-state message sits over the middle of a list or table.
class Overlay(QObject):
    def __init__(self, viewport: QWidget, message: QWidget) -> None:
        super().__init__(viewport)
        self.viewport = viewport
        self.message = message
        viewport.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.message.setGeometry(self.viewport.rect())

        return False
