import shutil
import threading

from PySide6.QtWidgets import (
    QFileDialog,
)

from ...system import open_in_system
from ..dialogs import ask_yes_no, show_message
from .state import CatalogTabState


class Folders(CatalogTabState):
    def pick_folder(self) -> str:
        return QFileDialog.getExistingDirectory(self.app, "Choose a folder", self.download_entry.text() or "")

    def browse_download(self) -> None:
        folder = self.pick_folder()

        if folder:
            self.download_entry.setText(folder)

    def move_download(self) -> None:
        if self.vault.busy():
            show_message(title="Moving", message="Wait for downloads to finish before moving.", parent=self.app)

            return

        folder = self.pick_folder()
        text = f"Move every download from\n{self.vault.download_dir or self.vault.root}\nto\n{folder}?"

        if folder and ask_yes_no(title="Move downloads", message=text, parent=self.app, action="Move"):
            threading.Thread(target=self.run_move, args=(folder,), daemon=True).start()

    def run_move(self, folder: str) -> None:
        try:
            new = self.vault.move_download_dir(new_dir=folder)

        except (OSError, ValueError, shutil.Error) as error:
            self.app.later(show_message, "Move failed", str(error) or type(error).__name__, self.app)

            return

        self.app.later(self.after_move, new)

    def after_move(self, new: str) -> None:
        self.download_entry.setText(new)
        show_message(title="Moved", message=f"Moved downloads to {new}", parent=self.app)

    def open_folder(self) -> None:
        self.vault.root.mkdir(parents=True, exist_ok=True)
        open_in_system(path=self.vault.root)
