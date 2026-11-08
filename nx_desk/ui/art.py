from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from .icon_set import icon
from .theme import COLORS

# Called on the UI thread only; painting from several threads at once crashed Qt.
SMOOTH = Qt.TransformationMode.SmoothTransformation
# The banner of a detail pane: drawn at twice this size, so it stays sharp when the pane is wide.
ART_SIZE = (412, 194)


def load_image(data: bytes) -> QImage | None:
    image = QImage()

    return image.convertToFormat(QImage.Format.Format_RGB32) if image.loadFromData(data) else None


def compose_banner(cover: QImage | None, background: QImage | None, size: tuple[int, int]) -> QImage:
    width, height = size
    source = background if background is not None else cover

    if source is None:
        raise ValueError("a banner needs a cover or a background")

    base = source.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, SMOOTH)
    base = base.copy((base.width() - width) // 2, (base.height() - height) // 2, width, height)

    if background is None:
        # Shrinking and growing again blurs the cover into a backdrop for itself.
        small = base.scaled(max(1, width // 14), max(1, height // 14), Qt.AspectRatioMode.IgnoreAspectRatio, SMOOTH)
        base = small.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, SMOOTH)

    base = base.convertToFormat(QImage.Format.Format_RGB32)
    painter = QPainter(base)
    painter.fillRect(base.rect(), QColor(0, 0, 0, 102))

    if cover is not None:
        # The margin follows the height, so a banner drawn larger keeps the same look when shown smaller.
        pad = max(4, height // 16)
        thumb = cover.scaled(width // 2, height - 2 * pad, Qt.AspectRatioMode.KeepAspectRatio, SMOOTH)
        top = (height - thumb.height()) // 2
        painter.setPen(QColor(0, 0, 0, 128))
        painter.drawRect(pad - 1, top - 1, thumb.width() + 1, thumb.height() + 1)
        painter.drawImage(pad, top, thumb)

    painter.end()

    return base


# A banner from the art files on disk, or None when neither one loads.
def banner_from_files(cover_path: Path | None, background_path: Path | None) -> QImage | None:
    try:
        cover, background = (
            load_image(data=path.read_bytes()) if path else None for path in (cover_path, background_path)
        )
    except OSError:
        return None

    if cover is None and background is None:
        return None

    width, height = ART_SIZE

    return compose_banner(cover=cover, background=background, size=(width * 2, height * 2))


# What stands in for a banner when there is no art: an icon on the panel colour, drawn at the banner's size.
def placeholder_image(icon_name: str) -> QImage:
    width, height = ART_SIZE
    image = QImage(width * 2, height * 2, QImage.Format.Format_RGB32)
    image.fill(QColor(COLORS["panel"]))
    size = height
    painter = QPainter(image)
    painter.setOpacity(0.45)
    painter.drawPixmap(
        (image.width() - size) // 2,
        (image.height() - size) // 2,
        icon(name=icon_name).pixmap(size, size),
    )
    painter.end()

    return image
