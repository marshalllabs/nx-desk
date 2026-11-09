from typing import Dict, List, Tuple, Union

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from ...schemas.card import Card
from ..icon_set import icon
from ..theme import COLORS, RADIUS
from .layout import CARD_ROLE, GAP, MARGIN, NAME_LINES, PAD, cover_size
from .thumbs import CoverThumbs

LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
BAR = 5


# The name on up to two lines: the second one is cut with an ellipsis when it does not fit.
def two_lines(metrics: QFontMetrics, text: str, width: int) -> List[str]:
    words = text.split()
    first = ""
    used = 0

    while used < len(words) and metrics.horizontalAdvance(f"{first} {words[used]}".strip()) <= width:
        first = f"{first} {words[used]}".strip()
        used += 1

    if not used:
        return [metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)]

    rest = " ".join(words[used:])

    return [first, metrics.elidedText(rest, Qt.TextElideMode.ElideRight, width)] if rest else [first]


# One row as a card: its cover (or an icon while it has none), then its title and subtitle. What the card shows
# comes from the model, as a Card under CARD_ROLE.
class CardDelegate(QStyledItemDelegate):
    def __init__(self, thumbs: CoverThumbs, parent: QListView) -> None:
        super().__init__(parent)
        self.thumbs = thumbs
        self.glyphs: Dict[Tuple[str, int], QPixmap] = {}

    # The grid sets the size of a cell, since it depends on the width of the view.
    def sizeHint(self, option: QStyleOptionViewItem, index: Union[QModelIndex, QPersistentModelIndex]) -> QSize:
        grid = self.parent()

        return grid.gridSize() if isinstance(grid, QListView) else option.rect.size()

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Union[QModelIndex, QPersistentModelIndex],
    ) -> None:
        card = index.data(CARD_ROLE)

        if not isinstance(card, Card):
            return

        frame = option.rect.adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(COLORS["select" if selected else "panel"]))
            painter.drawRoundedRect(frame, RADIUS, RADIUS)

        # The ring of the keyboard's card, like the ring around a table.
        if focused:
            painter.setPen(QPen(QColor(COLORS["focus"]), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(frame.adjusted(1, 1, -1, -1), RADIUS, RADIUS)

        cover = QRect(frame.x() + PAD, frame.y() + PAD, *cover_size(cell_width=option.rect.width()))
        self.paint_cover(painter=painter, cover=cover, card=card)
        self.paint_text(painter=painter, option=option, cover=cover, card=card, selected=selected)
        painter.restore()

    def paint_cover(self, painter: QPainter, cover: QRect, card: Card) -> None:
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(cover), RADIUS, RADIUS)
        painter.setClipPath(shape)
        painter.fillRect(cover, QColor(COLORS["panel"]))
        image = self.thumbs.get(key=card.key)

        if image is not None:
            painter.drawImage(cover, image)

        elif self.thumbs.shows_icon(key=card.key):
            # Looked up and none found, or no key: an icon, as the detail pane shows. While the art is still
            # fetched or being cut the card stays plain.
            size = cover.width() // 2
            painter.setOpacity(0.45)
            painter.drawPixmap(
                cover.x() + (cover.width() - size) // 2,
                cover.y() + (cover.height() - size) // 2,
                self.glyph(name=card.icon, size=size),
            )
            painter.setOpacity(1)

        # A transfer shows as a bar along the foot of the cover.
        if card.progress >= 0:
            painter.fillRect(cover.x(), cover.bottom() - BAR + 1, cover.width(), BAR, QColor(0, 0, 0, 170))
            done = round(number=cover.width() * min(1.0, card.progress))
            painter.fillRect(cover.x(), cover.bottom() - BAR + 1, done, BAR, QColor(COLORS["accent"]))

        painter.setClipping(False)

    # An SVG is drawn once for each size, not at every repaint.
    def glyph(self, name: str, size: int) -> QPixmap:
        key = (name, size)

        if key not in self.glyphs:
            self.glyphs[key] = icon(name=name).pixmap(size, size)

        return self.glyphs[key]

    @staticmethod
    def paint_text(painter: QPainter, option: QStyleOptionViewItem, cover: QRect, card: Card, selected: bool) -> None:
        font = QFont(option.font)
        metrics = QFontMetrics(font)
        line = metrics.height()
        top = cover.bottom() + 1 + GAP
        painter.setFont(font)
        painter.setPen(QColor(COLORS["ink"]))

        for number, text in enumerate(iterable=two_lines(metrics=metrics, text=card.title, width=cover.width())):
            painter.drawText(QRect(cover.x(), top + number * line, cover.width(), line), LEFT, text)

        # The muted text would fall under the contrast of the selected card, so it takes the plain colour there.
        tone = "ink" if selected and card.tone == "muted" else card.tone
        painter.setPen(QColor(COLORS[tone]))
        subtitle = metrics.elidedText(card.subtitle, Qt.TextElideMode.ElideRight, cover.width())
        painter.drawText(QRect(cover.x(), top + NAME_LINES * line, cover.width(), line), LEFT, subtitle)
