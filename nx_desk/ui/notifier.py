import shutil
import subprocess
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon


# Desktop notifications go through a tray icon, which also brings the window back. Desktops with
# no tray, such as plain GNOME, get them from notify-send when it is there.
class Notifier:
    def __init__(self, window: QMainWindow, icon_path: Path) -> None:
        self.window = window
        self.icon_path = icon_path
        # The app's own icon, in place of the system's blue "information" one.
        self.icon = QIcon(str(icon_path))
        self.tray: QSystemTrayIcon | None = None

        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.icon, window)
            self.tray.setToolTip("NX Desk")
            self.tray.activated.connect(lambda _reason: self.bring_up())
            self.tray.messageClicked.connect(self.bring_up)
            self.tray.show()

    def bring_up(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def show(self, title: str, text: str) -> None:
        if self.tray is not None and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, text, self.icon, 10000)

            return

        command = shutil.which(cmd="notify-send")

        if command:
            subprocess.Popen(
                args=[command, "--app-name=NX Desk", f"--icon={self.icon_path}", title, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
