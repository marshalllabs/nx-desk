import threading
from typing import TYPE_CHECKING

import shiboken6
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..schemas.github import Repo
from .icon_set import icon
from .rows import repo_labels
from .widgets.basics import button, chooser, label

if TYPE_CHECKING:
    from ..vault import Vault

COLUMNS = ("Repository", "Owner", "Visibility", "Updated", "Description")


# A button that shows the chosen repository by name, and its owner too when another one shares it.
# It is as wide as its text, which sets its size hint each time it changes.
def show_repo(widget: QPushButton, repo: str, repos: list[str]) -> None:
    chooser(
        widget=widget,
        text=repo_labels(repos=repos).get(repo, repo) if repo else "Choose a repository",
        tip=repo or "Choose a repository",
    )


# Lists every repository the user can reach, with the details that tell apart two of the same name.
class RepoPicker(QDialog):
    def __init__(self, parent: QWidget, vault: "Vault", current: str) -> None:
        super().__init__(parent)
        self.vault = vault
        self.current = current
        self.chosen = ""
        self.shown: int | None = None
        self.setWindowTitle("Choose a repository")
        self.resize(820, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        top = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Filter")
        self.query.setClearButtonEnabled(True)
        self.query.textChanged.connect(self.narrow)
        top.addWidget(self.query, 1)
        self.note = label(text="", role="muted")
        top.addWidget(self.note)
        self.reload_button = button(text="Reload", action=self.reload)
        self.reload_button.setIcon(icon(name="refresh"))
        top.addWidget(self.reload_button)
        layout.addLayout(top)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        # By name first; a click on a header sorts by that column instead.
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.itemSelectionChanged.connect(self.paint_choice)
        self.table.itemDoubleClicked.connect(lambda _: self.choose())
        layout.addWidget(self.table, 1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button(text="Cancel", action=self.reject))
        self.choose_button = button(text="Choose", action=self.choose, role="accent")
        self.choose_button.setDefault(True)
        foot.addWidget(self.choose_button)
        layout.addLayout(foot)
        # The list may still be loading, or reload while open, so the picker keeps watching it.
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.refill)
        self.timer.start()
        self.refill()

        if not self.vault.upload_snapshot().repos:
            self.reload()

    def refill(self) -> None:
        job = self.vault.upload_snapshot()
        busy = job.phase != "idle"
        self.reload_button.setEnabled(not busy)
        self.note.setText("Loading…" if busy else f"{len(job.repo_details)} repositories")

        if job.repo_list == self.shown:
            return

        self.shown = job.repo_list
        self.fill(repos=job.repo_details)

    def fill(self, repos: list[Repo]) -> None:
        picked = self.picked() or self.current
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(repos))

        for row, repo in enumerate(repos):
            texts = (
                repo.name or repo.full_name,
                repo.owner,
                repo.visibility.capitalize(),
                repo.updated_at[:10],
                repo.description,
            )

            for column, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                cell.setData(Qt.ItemDataRole.UserRole, repo.full_name)
                cell.setToolTip(repo.full_name if column == 0 else text)
                self.table.setItem(row, column, cell)

        self.table.setSortingEnabled(True)

        for row in range(self.table.rowCount()):
            first = self.table.item(row, 0)

            if first is not None and first.data(Qt.ItemDataRole.UserRole) == picked:
                self.table.selectRow(row)
                self.table.scrollToItem(first)

        self.narrow(text=self.query.text())
        self.paint_choice()

    # Filters on any column, such as an owner or a word of the description.
    def narrow(self, text: str) -> None:
        words = text.casefold().split()

        for row in range(self.table.rowCount()):
            line = " ".join(cell.text() for column in range(len(COLUMNS)) if (cell := self.table.item(row, column)))
            self.table.setRowHidden(row, not all(word in line.casefold() for word in words))

    def picked(self) -> str:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        cell = self.table.item(rows[0].row(), 0) if rows else None
        value = cell.data(Qt.ItemDataRole.UserRole) if cell is not None else ""

        return value if isinstance(value, str) else ""

    def paint_choice(self) -> None:
        self.choose_button.setEnabled(bool(self.picked()))

    def reload(self) -> None:
        if not self.vault.uploading():
            threading.Thread(target=self.vault.load_repos, daemon=True).start()

    def choose(self) -> None:
        self.chosen = self.picked()

        if self.chosen:
            self.accept()


# The chosen owner/name, or None when the picker was closed without one.
def pick_repo(parent: QWidget, vault: "Vault", current: str) -> str | None:
    picker = RepoPicker(parent=parent, vault=vault, current=current)
    accepted = picker.exec() == QDialog.DialogCode.Accepted
    chosen = picker.chosen
    shiboken6.delete(picker)

    return chosen if accepted else None
