from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QLabel,
)


# A text label that turns while something loads. It runs on its own timer, as the app repaints
# too slowly for it.
class Spinner:
    FRAMES = "◐◓◑◒"
    STEP = 120

    def __init__(self, target: QLabel) -> None:
        self.label = target
        self.text = ""
        self.frame = 0
        self.timer = QTimer(target)
        self.timer.setInterval(self.STEP)
        self.timer.timeout.connect(self.turn)

    def start(self, text: str) -> None:
        self.text = text

        if not self.timer.isActive():
            self.turn()
            self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def turn(self) -> None:
        self.frame = (self.frame + 1) % len(self.FRAMES)
        self.label.setText(f"{self.FRAMES[self.frame]}  {self.text}")
