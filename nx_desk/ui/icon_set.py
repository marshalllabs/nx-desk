from PySide6.QtGui import QIcon

from .style import ICONS

# One line style for every icon (Lucide-like, 2 px strokes), coloured with the theme's tokens.
ICON_SIZE = 16


def icon(name: str) -> QIcon:
    return QIcon(str(ICONS / f"{name}.svg"))


# For rich-text labels, which take an <img> rather than a QIcon.
def icon_html(name: str, size: int = 14) -> str:
    return f'<img src="{(ICONS / f"{name}.svg").as_posix()}" width="{size}" height="{size}">'
