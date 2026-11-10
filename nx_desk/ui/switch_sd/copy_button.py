from PySide6.QtCore import QSize, QTimer
from PySide6.QtWidgets import QToolButton

from ..icon_set import ICON_SIZE, icon
from ..style import set_role
from ..widgets.basics import copy_text


class CopyTitleButton(QToolButton):
    def __init__(self, title_id: str) -> None:
        super().__init__()
        self.title_id = title_id
        self.setFixedSize(32, 28)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.reset)
        self.clicked.connect(self.copy)
        self.reset()

    def copy(self) -> None:
        copy_text(text=self.title_id)
        self.mark_copied()

    def mark_copied(self) -> None:
        self.setIcon(icon(name="check"))
        self.setToolTip("Copied!")
        self.setAccessibleName(f"Copied Title ID {self.title_id}")
        set_role(widget=self, role="accent")
        self.timer.start()

    def reset(self) -> None:
        self.setIcon(icon(name="copy"))
        self.setToolTip(f"Copy Title ID {self.title_id} (Ctrl+C)")
        self.setAccessibleName(f"Copy Title ID {self.title_id}")
        set_role(widget=self, role="compact")
