from pathlib import Path
from typing import cast

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from .theme import COLORS, RADIUS

ICONS = Path(__file__).with_name(name="icons")

# Widgets pick a look through these properties, set with set_role, as a style sheet cannot read
# Python attributes.
STYLE_SHEET = """
QWidget {{ background: {bg}; color: {ink}; }}
QMainWindow, QDialog {{ background: {bg}; }}
QLabel[role="muted"] {{ color: {muted}; }}
QLabel[role="error"] {{ color: {bad}; }}
QLabel[role="title"] {{ font-size: {title_pt}pt; font-weight: bold; }}
QLabel[role="name"] {{ font-size: {name_pt}pt; font-weight: bold; }}
QLabel[role="strong"] {{ font-weight: bold; }}
QLabel[role="new"] {{ color: {ok}; font-weight: bold; }}
QLabel[role="update"] {{ color: {accent}; font-weight: bold; }}
QLabel[role="heading"] {{ color: {accent}; font-size: {small_pt}pt; font-weight: bold; }}
QLabel[role="key"] {{ color: {accent}; font-weight: bold; }}

/* Buttons: a visible edge in every state, the focus ring in the accent, and a disabled look that
   keeps the shape of a button. */
QPushButton, QToolButton {{
    background: {panel}; color: {ink}; border: 1px solid {border}; border-radius: {radius}px;
    padding: 5px 12px;
}}
QPushButton:hover, QToolButton:hover {{ background: {line}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {field}; }}
QPushButton:focus, QToolButton:focus {{ border-color: {focus}; }}
QPushButton:disabled, QToolButton:disabled {{ background: transparent; color: {muted}; border-color: {line}; }}
QPushButton[role="accent"] {{ background: {accent}; color: {accent_ink}; border-color: {accent}; font-weight: bold; }}
QPushButton[role="danger"] {{ background: {bad}; color: {accent_ink}; border-color: {bad}; font-weight: bold; }}
QPushButton:checked {{ background: {accent}; color: {accent_ink}; border-color: {accent}; }}
/* A tool button measures its text before the style sheet applies, so a bold one would be cut short. */
QToolButton[role="accent"] {{ background: {accent}; color: {accent_ink}; border-color: {accent}; }}
QToolButton[role="danger"] {{ background: {bad}; color: {accent_ink}; border-color: {bad}; }}
QPushButton[role="accent"]:hover, QToolButton[role="accent"]:hover {{ background: {accent_hover}; }}
QPushButton[role="danger"]:hover, QToolButton[role="danger"]:hover {{ background: {bad_hover}; }}
/* On a filled button the ring is drawn in the text colour, which stands out against the fill. */
QPushButton[role="accent"]:focus, QPushButton[role="danger"]:focus,
QToolButton[role="accent"]:focus, QToolButton[role="danger"]:focus {{ border-color: {ink}; }}
QPushButton[role="accent"]:disabled, QPushButton[role="danger"]:disabled,
QToolButton[role="accent"]:disabled, QToolButton[role="danger"]:disabled {{
    background: transparent; color: {muted}; border-color: {line};
}}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton[role="compact"] {{ padding: 5px 8px; }}
QPushButton[role="field"] {{
    background: {field}; border: 1px solid {border}; text-align: left; padding: 4px 8px;
}}
QPushButton[role="field"]:hover, QPushButton[role="field"]:focus {{ border-color: {focus}; }}
/* A thin vertical line between two groups of controls. */
QFrame[role="separator"] {{ background: {line}; border: none; }}
/* Two views of one tab: a quiet segmented pair, the chosen one underlined in the accent. */
QPushButton[role="segment"] {{ background: transparent; color: {muted}; border: 1px solid {line}; }}
QPushButton[role="segment"]:hover {{ background: {line}; color: {ink}; }}
QPushButton[role="segment-on"] {{
    background: {panel}; color: {ink}; border: 1px solid {border}; border-bottom: 2px solid {accent};
    font-weight: bold;
}}
QToolButton[popupMode="1"] {{ padding-right: 24px; }}
QToolButton::menu-button {{ border: none; border-left: 1px solid {border}; width: 18px; }}

QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser {{
    background: {field}; color: {ink}; border: 1px solid {border}; border-radius: {radius}px; padding: 4px 6px;
    selection-background-color: {select};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {focus}; }}
QLineEdit:disabled, QComboBox:disabled {{ color: {muted}; border-color: {line}; }}
QComboBox {{ combobox-popup: 0; }}
QFrame#choices {{ background: {panel}; border: 1px solid {border}; }}
QFrame#choices QLabel {{ background: transparent; }}
QFrame#choices QListWidget {{ background: {panel}; border: none; }}
QFrame#choices QListWidget::item {{ padding: 0 6px; border-radius: {radius}px; }}
QFrame#choices QListWidget::item:hover {{ background: {line}; }}
QComboBox QAbstractItemView {{
    background: {field}; color: {ink}; border: 1px solid {border}; selection-background-color: {select};
}}
QTextBrowser {{ border: none; background: {bg}; padding: 0; }}
QProgressBar {{ background: {field}; border: 1px solid {line}; border-radius: {radius}px; max-height: 8px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: {radius}px; }}

QGroupBox {{
    border: 1px solid {line}; border-radius: {radius}px; margin-top: 16px; padding: 10px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 0; padding: 0; color: {accent}; font-size: {small_pt}pt; font-weight: bold;
}}

/* Tabs: the chosen one is underlined rather than filled, so the accent stays for actions. */
QTabWidget::pane {{ border: 1px solid {line}; border-radius: {radius}px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 7px 16px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ background: {line}; color: {ink}; }}
QTabBar::tab:selected {{ color: {ink}; border-bottom: 2px solid {accent}; font-weight: bold; }}
QTabBar::tab:focus {{ background: {panel}; }}

/* Tables and trees: no dotted item focus, a ring around the whole view instead. */
QHeaderView::section {{
    background: {panel}; color: {muted}; border: none; border-bottom: 1px solid {line}; padding: 6px 8px;
}}
QTableView, QTreeView, QListWidget {{
    background: {field}; alternate-background-color: {field}; border: 1px solid transparent; outline: none;
    selection-background-color: {select}; selection-color: {ink}; gridline-color: {line};
}}
QTableView:focus, QTreeView:focus, QListWidget:focus {{ border-color: {focus}; }}
/* The Switch Ports grid: the same ground and ring as the table; its cards draw their own selection. */
QListView#grid {{ background: {field}; border: 1px solid transparent; outline: none; }}
QListView#grid:focus {{ border-color: {focus}; }}
/* Side padding keeps a right-aligned size apart from the left-aligned column after it. */
QTreeView::item, QTableView::item {{ padding: 4px 6px; }}
QTreeView::item:hover, QTableView::item:hover {{ background: {panel}; }}
QTreeView::item:selected, QTableView::item:selected {{ background: {select}; color: {ink}; }}

QMenuBar {{ background: {panel}; border-bottom: 1px solid {line}; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {line}; }}
QMenu {{ background: {panel}; border: 1px solid {border}; padding: 4px 0; }}
/* Room on the left for the toggle box, so every item's text starts at the same place. */
QMenu::item {{ padding: 5px 24px 5px 32px; }}
/* A toggle in a menu looks like a check box: a box when off, the accent and its tick when on. */
QMenu::indicator {{ width: 14px; height: 14px; left: 10px; }}
QMenu::indicator:non-exclusive:unchecked {{
    border: 1px solid {border}; border-radius: 3px; background: {field};
}}
QMenu::indicator:non-exclusive:checked {{
    border: 1px solid {accent}; border-radius: 3px; background: {accent}; image: url({icons}/check.svg);
}}
QMenu::indicator:disabled {{ border-color: {line}; }}
QMenu::item:selected {{ background: {line}; }}
QMenu::item:disabled {{ color: {muted}; }}
QMenu::separator {{ height: 1px; background: {line}; margin: 4px 8px; }}

/* Check boxes carry a tick, so a checked one does not rely on colour alone. */
QCheckBox {{ spacing: 6px; }}
QCheckBox:focus {{ color: {accent}; }}
QListWidget::indicator, QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {border}; border-radius: 3px; background: {field};
}}
QListWidget::indicator:checked, QCheckBox::indicator:checked {{
    background: {accent}; border-color: {accent}; image: url({icons}/check.svg);
}}
QCheckBox::indicator:disabled {{ border-color: {line}; background: transparent; }}
QCheckBox::indicator:checked:disabled {{ border-color: {line}; image: url({icons}/check_disabled.svg); }}
QCheckBox:disabled {{ color: {muted}; }}

/* Thin scroll bars in the theme, without arrow buttons. */
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {line}; border-radius: 4px; min-height: 28px; margin: 1px; }}
QScrollBar::handle:horizontal {{ background: {line}; border-radius: 4px; min-width: 28px; margin: 1px; }}
QScrollBar::handle:hover {{ background: {border}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; background: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {line}; }}
QToolTip {{ background: {panel}; color: {ink}; border: 1px solid {border}; padding: 4px; }}
"""


# Font sizes in points: the default, the range Settings offers (tables keep fixed row heights, so
# it stops at 14), and how much bigger titles are.
DEFAULT_FONT_SIZE = 10
FONT_SIZES = (8, 14)
TITLE_STEP = 5
NAME_STEP = 3
SMALL_STEP = -1


def default_family() -> str:
    return "Noto Sans" if "Noto Sans" in QFontDatabase.families() else QApplication.font().family()


def style_sheet(size: int) -> str:
    return STYLE_SHEET.format(
        **COLORS,
        radius=RADIUS,
        icons=ICONS.as_posix(),
        title_pt=size + TITLE_STEP,
        name_pt=size + NAME_STEP,
        small_pt=max(FONT_SIZES[0] - 1, size + SMALL_STEP),
    )


# The font comes first, so widgets measure their text in it. An empty family or a size of 0 keeps the default.
def apply_font(app: QApplication, family: str = "", size: int = 0) -> None:
    low, high = FONT_SIZES
    size = min(high, max(low, size)) if size else DEFAULT_FONT_SIZE
    app.setFont(QFont(family or default_family(), size))
    app.setStyleSheet(style_sheet(size=size))


def apply(app: QApplication, family: str = "", size: int = 0) -> None:
    app.setStyle("Fusion")
    colors = {name: QColor(value) for name, value in COLORS.items()}
    palette = QPalette()

    for role, color in (
        (QPalette.ColorRole.Window, "bg"),
        (QPalette.ColorRole.WindowText, "ink"),
        (QPalette.ColorRole.Base, "field"),
        (QPalette.ColorRole.AlternateBase, "panel"),
        (QPalette.ColorRole.Text, "ink"),
        (QPalette.ColorRole.Button, "panel"),
        (QPalette.ColorRole.ButtonText, "ink"),
        (QPalette.ColorRole.Highlight, "select"),
        (QPalette.ColorRole.HighlightedText, "ink"),
        (QPalette.ColorRole.ToolTipBase, "panel"),
        (QPalette.ColorRole.ToolTipText, "ink"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Link, "accent"),
        (QPalette.ColorRole.Mid, "line"),
    ):
        palette.setColor(role, colors[color])

    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, colors["muted"])

    app.setPalette(palette)
    apply_font(app=app, family=family, size=size)


def set_role(widget: QWidget, role: str | None) -> None:
    if widget.property("role") != role:
        widget.setProperty("role", role)
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def application() -> QApplication:
    # The UI always runs inside a QApplication, which instance() only types as its base class.
    return cast(QApplication, QApplication.instance())
