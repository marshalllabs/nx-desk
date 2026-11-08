from collections.abc import Callable

from PySide6.QtCore import QAbstractItemModel, QSize, Qt, QTimer
from PySide6.QtGui import QHideEvent, QResizeEvent, QShowEvent
from PySide6.QtWidgets import QAbstractItemView, QListView

from .delegate import CardDelegate
from .layout import cell_size, visible_slice
from .thumbs import CoverThumbs

# How often a grid in view looks for art and thumbnails that arrived, to draw its cards again.
REDRAW = 120


# The rows of a model as a wall of cards, so a tab can offer its table or this. `changes` tells when the art
# on disk has changed, so the cards are drawn again.
class CardGrid(QListView):
    def __init__(self, model: QAbstractItemModel, thumbs: CoverThumbs, changes: Callable[[], object]) -> None:
        super().__init__()
        self.thumbs = thumbs
        self.changes = changes
        self.setObjectName("grid")
        self.setModel(model)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(0)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always there, so its coming and going cannot change the width the cards are shared over.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setItemDelegate(CardDelegate(thumbs=thumbs, parent=self))
        self.fitted: tuple[int, int] | None = None
        self.signature: tuple[object, int] | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(REDRAW)
        self.timer.timeout.connect(self.redraw)
        self.fit_cells()

    # A cell is as wide as the view shares out and as tall as its cover and three lines of text, so a
    # change of window or font size changes it.
    def fit_cells(self) -> None:
        fit = (self.fontMetrics().height(), self.viewport().width())

        if fit != self.fitted:
            self.fitted = fit
            width, tall = cell_size(width=fit[1], line=fit[0])
            self.setGridSize(QSize(width, tall))

    # The cards are drawn again when more art or more thumbnails are ready.
    def redraw(self) -> None:
        signature = (self.changes(), self.thumbs.ready)

        if signature != self.signature:
            self.signature = signature
            self.viewport().update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fit_cells()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.timer.stop()

    # The rows in view and one row of cards after them.
    def shown_rows(self, total: int) -> tuple[int, int]:
        viewport = self.viewport()
        self.fit_cells()

        return visible_slice(
            scroll=self.verticalScrollBar().value(),
            width=viewport.width(),
            height=viewport.height(),
            cell=cell_size(width=viewport.width(), line=self.fontMetrics().height()),
            total=total,
        )
