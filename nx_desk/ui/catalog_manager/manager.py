import http.client
import threading
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...catalog.fields import MAPPABLE_FIELDS
from ...schemas.catalog import Catalog
from ...schemas.presentation import CatalogOutcome
from ..dialogs import ask_yes_no
from ..style import set_role
from ..widgets.basics import button, label
from ..widgets.spinner import Spinner
from .format_window import FormatWindow

if TYPE_CHECKING:
    from ..app import App


class CatalogManager(QDialog):
    MAX_ROWS = 8
    COLUMNS = (("Name", 150), ("Folder", 130), ("URL", 0), ("Field mapping", 130))

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.vault = app.vault
        # Set by the job thread: the state, the message and the folder of the edited catalog.
        self.outcome: Optional[CatalogOutcome] = None
        self.shown_folder: Optional[str] = None
        # The catalogs in the order the table shows them: by name.
        self.listed: List[Catalog] = []
        self.format_window: Optional[FormatWindow] = None
        self.setWindowTitle("Manage catalogs")
        # While open, the windows under it take no clicks or keys.
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(760)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        table = self.table = QTableWidget(0, len(self.COLUMNS))
        table.setHorizontalHeaderLabels([title for title, _ in self.COLUMNS])
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(28)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for index, (_, width) in enumerate(iterable=self.COLUMNS):
            if width:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
                header.resizeSection(index, width)

            else:
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)

        table.itemSelectionChanged.connect(self.picked)
        # Choosing a catalog is what this window is mostly for, so a double click does it.
        table.itemDoubleClicked.connect(lambda _: self.use())
        layout.addWidget(table)
        list_buttons = QHBoxLayout()
        list_buttons.addStretch(1)
        self.new_button = button(text="New catalog", action=self.clear)
        self.remove_button = button(text="Remove from list", action=self.remove, role="danger")
        # Switches the Catalog tab to the chosen catalog and closes this window.
        self.use_button = button(text="Use this catalog", action=self.use)
        list_buttons.addWidget(self.new_button)
        list_buttons.addWidget(self.remove_button)
        list_buttons.addWidget(self.use_button)
        layout.addLayout(list_buttons)

        fields = QGridLayout()
        fields.setHorizontalSpacing(8)
        fields.setColumnStretch(1, 1)
        fields.addWidget(label(text="Name", role="muted"), 0, 0)
        self.name = QLineEdit()
        fields.addWidget(self.name, 0, 1)
        fields.addWidget(label(text="URL", role="muted"), 1, 0)
        self.url = QLineEdit()
        self.url.returnPressed.connect(lambda: self.save() if self.chosen() else self.add())
        fields.addWidget(self.url, 1, 1)
        layout.addLayout(fields)

        # Advanced panel: an optional map from NXDesk's fields to this catalog's own keys,
        # for a JSON shape the heuristics do not recognise. Blank = pure auto-detect.
        toggles = QHBoxLayout()
        self.advanced = QCheckBox("Field mapping (advanced)")
        self.advanced.toggled.connect(self.toggle_advanced)
        toggles.addWidget(self.advanced)
        toggles.addStretch(1)
        toggles.addWidget(button(text="Catalog format", action=self.show_format))
        layout.addLayout(toggles)
        self.panel = QWidget()
        grid = QGridLayout(self.panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        hint = label(
            text="Leave blank to auto-detect. Enter the key name in the catalog JSON; use a dot to go into a "
            "sub-array, e.g. files.0.url.",
            role="muted",
        )
        hint.setWordWrap(True)
        grid.addWidget(hint, 0, 0, 1, 4)
        self.fields: Dict[str, QLineEdit] = {}

        for index, (field, text) in enumerate(iterable=MAPPABLE_FIELDS):
            entry = QLineEdit()
            self.fields[field] = entry
            row, column = 1 + index // 2, (index % 2) * 2
            grid.addWidget(label(text=text, role="muted"), row, column)
            grid.addWidget(entry, row, column + 1)

        self.panel.hide()
        layout.addWidget(self.panel)

        self.status = label(text="", role="muted")
        self.status.setWordWrap(True)
        self.spinner = Spinner(target=self.status)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.save_button = button(text="Save changes", action=self.save, role="accent")
        self.add_button = button(text="Add catalog", action=self.add, role="accent")
        actions.addWidget(self.save_button)
        actions.addWidget(self.add_button)
        layout.addLayout(actions)
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.wait_for_job)
        self.fill_list()
        self.url.setFocus()

    # No fixed height: the window follows its content, the list as tall as its catalogs.
    def fit(self) -> None:
        QTimer.singleShot(0, lambda: self.resize(self.width(), self.minimumSizeHint().height()))

    def show_format(self) -> None:
        if self.format_window is None:
            self.format_window = FormatWindow(parent=self)

        self.format_window.show()
        self.format_window.raise_()

    def toggle_advanced(self, shown: bool) -> None:
        self.panel.setVisible(shown)
        self.fit()

    def current_mapping(self) -> Dict[str, str]:
        return {field: entry.text() for field, entry in self.fields.items() if entry.text().strip()}

    # Shows the list again each time the window opens, with the catalog in use chosen.
    def prepare(self) -> None:
        self.fill_list()
        active = self.vault.catalog.folder if self.vault.catalog else None
        folders = [catalog.folder for catalog in self.listed]

        if active in folders:
            self.table.selectRow(folders.index(active))

        else:
            self.clear()

        self.status.setText("")
        self.url.setFocus()

    def fill_list(self) -> None:
        # By name, whatever order they were added in.
        catalogs = self.listed = sorted(
            self.vault.catalogs,
            key=lambda catalog: (catalog.name.casefold(), catalog.folder),
        )
        self.table.blockSignals(True)
        self.table.setRowCount(len(catalogs))

        for row, catalog in enumerate(iterable=catalogs):
            values = (
                catalog.name,
                catalog.folder,
                catalog.url,
                "Custom" if catalog.mapping else "Auto",
            )

            for column, value in enumerate(iterable=values):
                self.table.setItem(row, column, QTableWidgetItem(value))

        self.table.blockSignals(False)
        rows = min(self.MAX_ROWS, max(1, len(catalogs)))
        height = (
            self.table.horizontalHeader().sizeHint().height() + rows * self.table.verticalHeader().defaultSectionSize()
        )
        self.table.setFixedHeight(height + 2)
        self.paint_buttons()
        self.fit()

    def chosen(self) -> Optional[Catalog]:
        rows = self.table.selectionModel().selectedRows()
        index = rows[0].row() if rows else -1

        return self.listed[index] if 0 <= index < len(self.listed) else None

    # Picking a catalog loads it into the fields below, which then save back to it.
    # The table picks a saved catalog again after a reload; that must not wipe the result shown.
    def picked(self) -> None:
        catalog = self.chosen()
        folder = catalog.folder if catalog else None

        if catalog and folder != self.shown_folder:
            self.name.setText(catalog.name)
            self.url.setText(catalog.url)
            mapping = catalog.mapping or {}

            for field, entry in self.fields.items():
                entry.setText(mapping.get(field, ""))

            self.advanced.setChecked(bool(mapping))
            self.status.setText("")

        self.shown_folder = folder
        self.paint_buttons()

    def clear(self) -> None:
        self.table.clearSelection()
        self.name.clear()
        self.url.clear()

        for entry in self.fields.values():
            entry.clear()

        self.advanced.setChecked(False)
        self.paint_buttons()

    def paint_buttons(self) -> None:
        chosen = self.chosen()
        editing = chosen is not None
        active = self.vault.catalog.folder if self.vault.catalog else None
        # Only a catalog that is not in use can be switched to.
        usable = chosen is not None and chosen.folder != active
        self.use_button.setEnabled(usable)
        set_role(widget=self.use_button, role="accent" if usable else None)
        self.remove_button.setEnabled(editing)
        self.new_button.setEnabled(editing)
        set_role(widget=self.add_button, role=None if editing else "accent")
        self.save_button.setVisible(editing)

    def run(self, job: Callable[[], None], message: str) -> None:
        if self.outcome is not None or self.timer.isActive():
            return

        for widget in (self.add_button, self.save_button):
            widget.setEnabled(False)

        set_role(widget=self.status, role="muted")
        self.spinner.start(text=message)
        threading.Thread(target=job, daemon=True).start()
        self.timer.start()

    def add(self) -> None:
        name, url, mapping = self.name.text(), self.url.text(), self.current_mapping()

        def job() -> None:
            try:
                catalog = self.vault.add_catalog(name=name, url=url, mapping=mapping)
                self.outcome = CatalogOutcome(
                    state="ok",
                    message=f"Added {catalog.name} ({len(self.vault.items)} games).",
                )

            except (OSError, ValueError, http.client.HTTPException) as error:
                self.outcome = CatalogOutcome(state="error", message=str(error) or type(error).__name__)

        self.run(job=job, message="Reading catalog…")

    def save(self) -> None:
        catalog = self.chosen()

        if not catalog:
            return

        folder, name, url, mapping = catalog.folder, self.name.text(), self.url.text(), self.current_mapping()

        def job() -> None:
            try:
                edit = self.vault.edit_catalog(folder=folder, name=name, url=url, mapping=mapping)
                message = " ".join([f"Saved {edit.catalog.name} ({edit.count} games).", *edit.notes])
                # The folder may have followed a new name, so the list picks the catalog by its folder now.
                self.outcome = CatalogOutcome(state="ok", message=message, edited=edit.catalog.folder)

            except (OSError, ValueError, http.client.HTTPException) as error:
                self.outcome = CatalogOutcome(state="error", message=str(error) or type(error).__name__, edited=folder)

        self.run(job=job, message="Reading catalog…")

    def wait_for_job(self) -> None:
        if self.outcome is None:
            return

        self.timer.stop()
        state, message, edited = self.outcome.state, self.outcome.message, self.outcome.edited
        self.outcome = None
        self.spinner.stop()

        for widget in (self.add_button, self.save_button):
            widget.setEnabled(True)

        self.status.setText(message)
        set_role(widget=self.status, role="muted" if state == "ok" else "error")

        if state == "ok" and edited:
            self.fill_list()
            folders = [catalog.folder for catalog in self.listed]

            if edited in folders:
                # Picking the saved catalog again must not wipe the message that was just set.
                self.shown_folder = edited
                self.table.selectRow(folders.index(edited))

            self.paint_buttons()
            self.app.catalog.detail_key = None

        elif state == "ok":
            self.name.clear()
            self.url.clear()

            for entry in self.fields.values():
                entry.clear()

            self.fill_list()

    # Switches the Catalog tab to the chosen catalog, then closes; nothing changes while a download runs.
    def use(self) -> None:
        catalog = self.chosen()

        if catalog and self.app.catalog.switch_catalog(folder=catalog.folder, parent=self):
            self.accept()

    def remove(self) -> None:
        catalog = self.chosen()

        if not catalog:
            return

        if self.vault.busy() and catalog is self.vault.catalog:
            self.status.setText("Wait for downloads to finish.")
            set_role(widget=self.status, role="error")

            return

        if ask_yes_no(
            title="Remove catalog",
            message=f"Remove {catalog.name} from the list? Its saved data and art are deleted; downloaded files are kept.",
            parent=self,
            action="Remove",
            danger=True,
        ):
            self.vault.remove_catalog(folder=catalog.folder)
            self.fill_list()
            self.clear()
