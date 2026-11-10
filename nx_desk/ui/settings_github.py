from typing import TYPE_CHECKING, Callable

from PySide6.QtWidgets import QFormLayout, QGroupBox, QHBoxLayout, QLineEdit

from .theme import SPACE
from .widgets.basics import button, label

if TYPE_CHECKING:
    from ..vault import Vault


class GitHubSettings(QGroupBox):
    def __init__(self, vault: "Vault", changed: Callable[[], None]) -> None:
        super().__init__("GitHub")
        self.vault = vault
        self.changed = changed
        self.forget = False
        self.form = QFormLayout(self)
        self.form.setHorizontalSpacing(SPACE["md"])
        self.form.setVerticalSpacing(SPACE["sm"])
        self.entry = QLineEdit()
        self.entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.entry.setAccessibleName("GitHub personal access token")
        self.entry.setMinimumWidth(200)
        self.entry.textChanged.connect(lambda _: self.changed())
        self.show_button = button(text="Show", action=self.toggle)
        self.show_button.setToolTip("Show or hide the token you are typing")
        self.remove = button(text="Remove", action=self.clear)
        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        row.addWidget(self.entry, 1)
        row.addWidget(self.show_button)
        row.addWidget(self.remove)
        self.form.addRow("Personal access token", row)
        self.note = label(text="", role="muted")
        self.note.setWordWrap(True)
        self.form.addRow("", self.note)
        self.error = label(text="", role="error")
        self.error.setWordWrap(True)
        self.form.addRow("", self.error)
        self.error.hide()
        permissions = label(text="Select the destination repositories with Contents: Read and write.", role="muted")
        permissions.setWordWrap(True)
        self.form.addRow("Permissions", permissions)
        self.paint()

    def paint(self) -> None:
        saved = self.vault.github_token_saved and not self.forget
        self.entry.setPlaceholderText(
            "A token is saved; paste another to replace it" if saved else "Paste a GitHub PAT",
        )
        self.remove.setEnabled(saved)
        self.note.setText(
            "Removed when you apply."
            if self.forget
            else "Saved in the system keyring."
            if saved
            else "No token saved.",
        )

    def toggle(self) -> None:
        hidden = self.entry.echoMode() == QLineEdit.EchoMode.Password
        self.entry.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.show_button.setText("Hide" if hidden else "Show")

    def clear(self) -> None:
        self.forget = True
        self.entry.clear()
        self.paint()
        self.changed()

    def pending(self) -> bool:
        return bool(self.entry.text().strip()) or self.forget

    def apply(self) -> bool:
        if not self.pending():
            return True

        try:
            self.vault.set_github_token(token=self.entry.text())

        except ValueError as error:
            self.error.setText(str(error))
            self.error.show()
            self.entry.setFocus()

            return False

        self.forget = False
        self.entry.clear()
        self.entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_button.setText("Show")
        self.error.clear()
        self.error.hide()
        self.paint()

        return True
