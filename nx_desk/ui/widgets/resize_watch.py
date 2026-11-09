from typing import Callable

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QWidget


# Calls back whenever a widget changes size, such as to fit a picture to a pane the user drags wider.
class ResizeWatch(QObject):
    def __init__(self, widget: QWidget, changed: Callable[[], None]) -> None:
        super().__init__(widget)
        self.changed = changed
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self.changed()

        return False
