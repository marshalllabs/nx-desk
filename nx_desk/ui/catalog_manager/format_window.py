import html
import json
from typing import Iterable, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...catalog.fields import CATALOG_TEMPLATE, FIELD_ALIASES, ROOT_ALIASES
from ...schemas.presentation import FieldRow
from ..theme import COLORS
from ..widgets.basics import button, copy_text, label
from .json_highlighter import JsonHighlighter

# A row of the format window: the key, its type and the other names read for it.
# Format rows use the shared FieldRow schema.


# What a catalog needs to be read without a field mapping: the fields in two sections, each with
# the other key names read in its place, and a template to copy.
class FormatWindow(QDialog):
    REQUIRED = ("id", "title_id", "url")
    TYPES = {
        "id": "text",
        "title_id": "16 hex characters",
        "sha256": "64 hex characters",
        "size": "bytes",
        "url": "HTTPS URL",
        "mirrors": "list of URLs",
        "tags": "list of text",
        "description": "list of text",
        "highlights": "list of {title, text}",
        "done": "list of text",
        "kept": "list of text",
        "cover": "HTTPS URL",
        "background": "HTTPS URL",
    }
    # The whole window stays within this share of the screen's height, leaving room for panels.
    SCREEN_SHARE = 0.8

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.template = json.dumps(obj=CATALOG_TEMPLATE.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        self.setWindowTitle("Catalog format")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(12, 4, 12, 12)
        column.setSpacing(8)
        keys = list(type(CATALOG_TEMPLATE.mods[0]).model_fields)
        column.addWidget(
            self.section(
                title="Games list",
                rows=[FieldRow(key="mods", kind="array of games, or the whole file is one", aliases=ROOT_ALIASES[1:])],
            ),
        )
        column.addWidget(
            self.section(title="Required", rows=[self.field(key=key) for key in keys if key in self.REQUIRED]),
        )
        column.addWidget(
            self.section(title="Optional", rows=[self.field(key=key) for key in keys if key not in self.REQUIRED]),
        )
        column.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        tabs.addTab(scroll, "Fields")
        text = QPlainTextEdit(self.template)
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.highlighter = JsonHighlighter(document=text.document())
        tabs.addTab(text, "Template")
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button(text="Close", action=self.close))
        self.copy_button = button(text="Copy template", action=self.copy, role="accent")
        buttons.addWidget(self.copy_button)
        layout.addLayout(buttons)
        page.adjustSize()
        screen = self.screen().availableGeometry() if self.screen() else None
        wanted = page.sizeHint().height() + 120
        room = int(screen.height() * self.SCREEN_SHARE) if screen else wanted
        self.resize(page.sizeHint().width() + 60, min(wanted, room))

    def field(self, key: str) -> FieldRow:
        names = next((names for names in FIELD_ALIASES.values() if names[0] == key), [key])

        return FieldRow(key=key, kind=self.TYPES.get(key, "text"), aliases=names[1:])

    # Each other name is a chip, like the genres in the Catalog tab; no-break spaces pad a chip, so
    # a line only breaks between chips.
    @staticmethod
    def chips(names: Sequence[str]) -> str:
        if not names:
            return f'<span style="color:{COLORS["muted"]}">-</span>'

        return "&nbsp; ".join(
            f'<span style="background-color:{COLORS["panel"]}; font-size:9pt">&nbsp;{html.escape(s=name)}&nbsp;</span>'
            for name in names
        )

    def section(self, title: str, rows: Iterable[FieldRow]) -> QGroupBox:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnMinimumWidth(1, 300)
        grid.setColumnStretch(2, 1)

        for column, text in enumerate(iterable=("Key", "Type", "Also read as")):
            grid.addWidget(label(text=text, role="muted"), 0, column)

        for index, field in enumerate(iterable=rows, start=1):
            key, kind, names = field.key, field.kind, field.aliases
            grid.addWidget(label(text=key, role="key"), index, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(label(text=kind, role="muted"), index, 1, Qt.AlignmentFlag.AlignTop)
            chips = QLabel(self.chips(names=names))
            chips.setWordWrap(True)
            chips.setMinimumWidth(380)
            grid.addWidget(chips, index, 2)

        return box

    def copy(self) -> None:
        copy_text(text=self.template)
        self.copy_button.setText("Copied")
        QTimer.singleShot(1500, lambda: self.copy_button.setText("Copy template"))
