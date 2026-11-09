import math
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...catalog.ports import HOSTS
from ...schemas.port import Port
from ..art import ART_SIZE
from ..theme import SPACE
from ..widgets.basics import button, label
from ..widgets.resize_watch import ResizeWatch
from .detail_html import detail_html
from .model import type_text


# The pane beside the table: the banner, the name, the links and the details of the chosen entry.
class PortDetail(QStackedWidget):
    def __init__(self) -> None:
        super().__init__()
        self.shown: Optional[str] = None
        self.art_image: Optional[QImage] = None
        # The banner scales with the pane, so it can be dragged much wider than its base size.
        self.setMinimumWidth(ART_SIZE[0] + SPACE["sm"])
        self.setMaximumWidth(900)
        page = QWidget()
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)
        self.art = label()
        self.art.hide()
        column.addWidget(self.art)
        self.name = label(text="", role="name")
        self.name.setWordWrap(True)
        column.addWidget(self.name)
        self.subtitle = label(text="", role="muted")
        self.subtitle.setWordWrap(True)
        column.addWidget(self.subtitle)
        links = QHBoxLayout()
        links.setSpacing(SPACE["sm"])
        self.repo_button = button(text="Open page", role="accent")
        self.thread_button = button(text="Open thread")
        links.addWidget(self.repo_button)
        links.addWidget(self.thread_button)
        links.addStretch(1)
        column.addLayout(links)
        self.text = QTextBrowser()
        self.text.setOpenLinks(False)
        self.text.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        column.addWidget(self.text)
        self.hint = label(text="Add a SteamGridDB key in Settings to show artwork.", role="muted")
        self.hint.setWordWrap(True)
        self.hint.hide()
        column.addWidget(self.hint)
        column.addStretch(1)
        self.pane = QScrollArea()
        self.pane.setWidgetResizable(True)
        self.pane.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pane.setWidget(page)
        ResizeWatch(widget=self.pane.viewport(), changed=self.fit)
        self.addWidget(self.pane)
        empty = label(text="No entry selected", role="muted")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addWidget(empty)
        self.setCurrentIndex(1)

    def show_port(self, port: Optional[Port], banner: Optional[QImage], needs_key: bool) -> None:
        key = port.id if port else None

        if key != self.shown:
            self.shown = key
            self.art_image = None
            self.art.hide()
            self.setCurrentIndex(0 if port else 1)

            if port:
                host = HOSTS.get(port.host)
                self.name.setText(port.name)
                self.subtitle.setText(f"{port.platform} · {type_text(port=port)}")
                self.repo_button.setText(f"Open on {host}" if host else "Open page")
                self.repo_button.setEnabled(bool(port.url))
                self.thread_button.setEnabled(bool(port.thread))
                self.text.setHtml(detail_html(port=port))
                self.fit_text()

        self.hint.setVisible(port is not None and needs_key)

        if banner is not None and banner is not self.art_image:
            self.art_image = banner
            self.fit_art()
            self.art.show()

    # The banner fills the pane's width at its own aspect, so dragging the pane wider leaves no gap.
    def fit_art(self) -> None:
        if self.art_image is None:
            return

        width = max(1, self.pane.viewport().width())
        height = round(number=width * ART_SIZE[1] / ART_SIZE[0])
        picture = QPixmap.fromImage(self.art_image).scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.art.setPixmap(picture)
        self.art.setFixedHeight(picture.height())

    # The text is as tall as its content at the width it has now, so the whole pane scrolls as one.
    def fit_text(self) -> None:
        document = self.text.document()
        document.setTextWidth(self.text.viewport().width())
        frame = 2 * self.text.frameWidth()
        self.text.setFixedHeight(math.ceil(document.size().height()) + frame)

    def fit(self) -> None:
        self.fit_art()
        self.fit_text()
