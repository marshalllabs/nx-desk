import functools
from typing import Callable, Dict, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QWidget,
)

from ..style import set_role
from .basics import button

VIEWS = (("list", "List"), ("log", "Log"))


# A quiet row of views of one tab, the chosen one underlined: List and Log, or List, Grid and Log.
class ViewSwitch(QWidget):
    def __init__(
        self,
        swap: Callable[[str], None],
        views: Tuple[Tuple[str, str], ...] = VIEWS,
        bottom: int = 4,
    ) -> None:
        super().__init__()
        self.swap = swap
        self.views = list(views)
        self.shown = ""
        self.buttons: Dict[str, QPushButton] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, bottom)
        layout.setSpacing(0)

        for view, text in views:
            tab = button(text=text, action=functools.partial(self.show_view, view))

            tab.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tab.setMinimumWidth(88)
            tab.setCheckable(False)
            layout.addWidget(tab)
            self.buttons[view] = tab

    # A tab may change its name with what it shows, such as List and Grid for the games.
    def rename(self, view: str, text: str) -> None:
        self.views = [(name, text if name == view else old) for name, old in self.views]
        self.buttons[view].setText(text)
        self.paint(view=self.shown)

    def show_view(self, view: str) -> None:
        self.swap(view)
        self.paint(view=view)

    def paint(self, view: str) -> None:
        self.shown = view

        # A quiet row: the accent stays for the tab's real actions.
        for name, text in self.views:
            chosen = name == view
            set_role(widget=self.buttons[name], role="segment-on" if chosen else "segment")
            self.buttons[name].setAccessibleName(f"{text} view" + (" (shown)" if chosen else ""))
