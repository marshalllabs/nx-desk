from typing import TYPE_CHECKING

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..config import COMPRESSION_LEVELS
from ..names import SIZE_UNITS
from .style import DEFAULT_FONT_SIZE, FONT_SIZES, default_family
from .theme import SPACE
from .widgets.basics import button, label

if TYPE_CHECKING:
    from .app import App

UNIT_NAMES = {"binary": "Binary (1024, GiB)", "decimal": "Decimal (1000, GB)"}
KEY_PLACES = {
    "": "Not set: game art comes from the catalog.",
    "keyring": "Saved in the system keyring.",
    "sealed": "No system keyring here, so the key is sealed in the data folder.",
}


# Choices wait until Apply, which keeps the window open, or Save, which also closes it. Cancel, or
# closing the window, drops what was not applied yet.
class SettingsWindow(QDialog):
    def __init__(self, app: "App") -> None:
        super().__init__(app)
        self.app = app
        self.vault = app.vault
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self.forms: list[QFormLayout] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(self.build_appearance())
        layout.addWidget(self.build_downloads())
        layout.addWidget(self.build_art())
        layout.addWidget(self.build_other())
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(button(text="Cancel", action=self.reject))
        self.apply_button = button(text="Apply", action=self.apply)
        foot.addWidget(self.apply_button)
        save = button(text="Save", action=self.save, role="accent")
        save.setDefault(True)
        foot.addWidget(save)
        layout.addLayout(foot)
        self.align_labels()
        self.paint_pending()

    def group(self, title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setHorizontalSpacing(SPACE["md"])
        form.setVerticalSpacing(SPACE["sm"])
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.forms.append(form)

        return box, form

    # Every group gets the widest label's width, so the fields of all groups line up.
    def align_labels(self) -> None:
        labels = [
            widget
            for form in self.forms
            for row in range(form.rowCount())
            if (item := form.itemAt(row, QFormLayout.ItemRole.LabelRole)) and (widget := item.widget())
        ]
        width = max((widget.sizeHint().width() for widget in labels), default=0)

        for widget in labels:
            widget.setMinimumWidth(width)

    def build_appearance(self) -> QGroupBox:
        box, form = self.group(title="Appearance")
        self.family_box = QFontComboBox()
        # Its own size hint fits the longest family name, which left the "Font" label no room.
        self.family_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.family_box.setMinimumContentsLength(16)
        self.family_box.setCurrentFont(QFont(self.vault.font_family or default_family()))
        self.size_box = QSpinBox()
        self.size_box.setRange(*FONT_SIZES)
        self.size_box.setSuffix(" pt")
        self.size_box.setValue(self.vault.font_size or DEFAULT_FONT_SIZE)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.family_box, 1)
        row.addWidget(self.size_box)
        row.addWidget(button(text="Default", action=self.default_font))
        form.addRow("Font", row)
        self.family_box.currentFontChanged.connect(lambda _: self.paint_pending())
        self.size_box.valueChanged.connect(lambda _: self.paint_pending())

        return box

    def build_downloads(self) -> QGroupBox:
        box, form = self.group(title="Downloads")
        self.compression = QComboBox()

        for text, level in COMPRESSION_LEVELS:
            self.compression.addItem(text, level)

        self.compression.setCurrentIndex(self.compression.findData(self.vault.compression))
        self.compression.activated.connect(lambda _: self.paint_pending())
        form.addRow("Repack compression", self.compression)
        self.units = QComboBox()

        for units in SIZE_UNITS:
            self.units.addItem(UNIT_NAMES[units], units)

        self.units.setCurrentIndex(self.units.findData(self.vault.size_units))
        self.units.activated.connect(lambda _: self.paint_pending())
        form.addRow("Size units", self.units)

        return box

    # The key is never shown back: the field only takes a new one, and Remove forgets the saved one.
    def build_art(self) -> QGroupBox:
        box, form = self.group(title="Game art")
        self.forget_key = False
        self.key_entry = QLineEdit()
        self.key_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_entry.setMinimumWidth(200)
        self.key_entry.setAccessibleName("SteamGridDB API key")
        self.key_entry.textChanged.connect(lambda _: self.paint_pending())
        # Only what is being typed can be shown; the saved key never comes back to the window.
        self.show_key = button(text="Show", action=self.toggle_key)
        self.show_key.setToolTip("Show or hide the key you are typing")
        self.remove_key = button(text="Remove", action=self.remove_art_key)
        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        row.addWidget(self.key_entry, 1)
        row.addWidget(self.show_key)
        row.addWidget(self.remove_key)
        form.addRow("SteamGridDB key", row)
        self.key_note: QLabel = label(text="", role="muted")
        self.key_note.setWordWrap(True)
        form.addRow("", self.key_note)
        self.paint_key()

        return box

    def paint_key(self) -> None:
        place, error = self.vault.art_status()
        saved = place != "" and not self.forget_key
        self.key_entry.setPlaceholderText(
            "A key is saved; paste another to replace it" if saved else "Paste a key from steamgriddb.com",
        )
        self.remove_key.setEnabled(saved)
        note = "Removed when you apply." if self.forget_key else KEY_PLACES[place]
        self.key_note.setText(f"{note} {error}." if error and saved else note)

    def toggle_key(self) -> None:
        hidden = self.key_entry.echoMode() == QLineEdit.EchoMode.Password
        self.key_entry.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.show_key.setText("Hide" if hidden else "Show")

    def remove_art_key(self) -> None:
        self.forget_key = True
        self.key_entry.clear()
        self.paint_key()
        self.paint_pending()

    def build_other(self) -> QGroupBox:
        box, form = self.group(title="Notifications and logs")
        self.notify = QCheckBox("Show desktop notifications")
        self.notify.setToolTip("For new or changed mods and finished runs")
        self.notify.setChecked(self.vault.notify)
        self.notify.toggled.connect(lambda _: self.paint_pending())
        form.addRow("Notifications", self.notify)
        logs = QHBoxLayout()
        logs.addWidget(button(text="Open log folder", action=self.app.open_logs))
        logs.addStretch(1)
        form.addRow("Logs", logs)

        return box

    # The values as they would be saved; the default font is saved as empty, so a later default
    # still reaches it.
    def chosen(self) -> tuple[str, int, object, str, bool, str, bool]:
        family = self.family_box.currentFont().family()
        size = self.size_box.value()

        return (
            "" if family == default_family() else family,
            0 if size == DEFAULT_FONT_SIZE else size,
            self.compression.currentData(),
            str(self.units.currentData()),
            self.notify.isChecked(),
            self.key_entry.text().strip(),
            self.forget_key,
        )

    def saved(self) -> tuple[str, int, object, str, bool, str, bool]:
        vault = self.vault

        return vault.font_family, vault.font_size, vault.compression, vault.size_units, vault.notify, "", False

    def paint_pending(self) -> None:
        self.apply_button.setEnabled(self.chosen() != self.saved())

    # Only what changed is applied, so an unchanged font does not restyle the whole window.
    def apply(self) -> None:
        family, size, compression, units, notify, key, forget = self.chosen()

        if (family, size) != (self.vault.font_family, self.vault.font_size):
            self.app.set_font(family=family, size=size)

        if compression != self.vault.compression and isinstance(compression, int):
            self.vault.set_compression(level=compression)

        if units != self.vault.size_units:
            self.app.units_changed(units=units)

        if notify != self.vault.notify:
            self.vault.set_notify(enabled=notify)

        if key or forget:
            self.vault.set_art_key(key=key)
            self.forget_key = False
            self.key_entry.clear()
            self.key_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.show_key.setText("Show")
            self.paint_key()

        self.paint_pending()

    def save(self) -> None:
        self.apply()
        self.accept()

    def default_font(self) -> None:
        self.family_box.setCurrentFont(QFont(default_family()))
        self.size_box.setValue(DEFAULT_FONT_SIZE)
