from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QPushButton, QSizePolicy, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget

from ...schemas.homebrew import Homebrew
from ..art import ART_SIZE
from ..widgets.basics import button, label
from ..widgets.resize_watch import ResizeWatch


class HomebrewDetail(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.shown: Optional[Homebrew] = None
        self.art_image: Optional[QImage] = None
        self.setMinimumWidth(280)
        self.setMaximumWidth(700)
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        self.art = label()
        self.art.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.art.hide()
        column.addWidget(self.art)
        self.name = label(role="name")
        self.name.setWordWrap(True)
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        column.addWidget(self.name)
        self.open_button: QPushButton = button(text="Open page", role="accent")
        column.addWidget(self.open_button)
        self.hint = label(text="Add a SteamGridDB key in Settings to show artwork.", role="muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        column.addWidget(self.hint)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        column.addWidget(self.text, 1)
        self.addWidget(page)
        empty = label(text="Select a homebrew to see its details", role="muted")
        empty.setWordWrap(True)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addWidget(empty)
        self.setCurrentIndex(1)
        ResizeWatch(widget=self.art, changed=self.fit_art)

    def show_entry(self, row: Optional[Homebrew], banner: Optional[QImage], needs_key: bool) -> None:
        self.setCurrentIndex(0 if row else 1)
        self.hint.setVisible(row is not None and needs_key)

        if row is None:
            self.shown = None
            self.art_image = None
            self.art.hide()

            return

        if banner is not self.art_image:
            self.art_image = banner
            self.art.setVisible(banner is not None)
            self.fit_art()

        if row == self.shown:
            return

        self.shown = row
        self.name.setText(row.name)
        self.open_button.setEnabled(bool(row.url))
        metadata = (
            ("Group", ", ".join(row.groups)),
            ("Type", row.category),
            ("Version", row.version),
            ("Authors", row.authors),
            ("Updated", row.updated),
        )
        lines = [f"{title}: {value}" for title, value in metadata if value]
        self.text.setPlainText("\n".join(lines) + "\n\n" + row.description)

    def fit_art(self) -> None:
        if self.art_image is None:
            return

        width = max(1, self.art.width())
        height = round(number=width * ART_SIZE[1] / ART_SIZE[0])
        image = QPixmap.fromImage(self.art_image).scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.art.setPixmap(image)
        self.art.setFixedHeight(image.height())
