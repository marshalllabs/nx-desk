from collections.abc import Callable, Iterable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from ..icon_set import ICON_SIZE, icon
from ..style import set_role


def label(text: str = "", role: str | None = None, parent: QWidget | None = None) -> QLabel:
    widget = QLabel(text, parent)

    if role:
        set_role(widget=widget, role=role)

    return widget


def button(
    text: str,
    action: Callable[[], object] | None = None,
    role: str | None = None,
    parent: QWidget | None = None,
) -> QPushButton:
    widget = QPushButton(text, parent)
    widget.setAutoDefault(False)

    if role:
        set_role(widget=widget, role=role)

    if action:
        widget.clicked.connect(lambda: action())

    return widget


# The side padding style.py gives buttons, and the room of a menu arrow beside one.
TOOL_PADDING = 28
TOOL_ARROW = 24


# Fills a menu; None in entries puts a separator there.
def fill_menu(menu: QMenu, entries: Iterable[QAction | None]) -> QMenu:
    for entry in entries:
        if entry is None:
            menu.addSeparator()
        else:
            menu.addAction(entry)

    return menu


# A tool button leaves the style sheet's side padding out of its size, which cut its text short,
# so this one adds it back. It measures in its current font, so a font change resizes it.
class FitButton(QToolButton):
    def __init__(self, room: int) -> None:
        super().__init__()
        self.room = room

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()

        return QSize(max(hint.width(), self.fontMetrics().horizontalAdvance(self.text()) + self.room), hint.height())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


# A button that shows an action: its text, or its icon text when the action has a short one, and
# whether it is enabled. With menu entries, an arrow beside it opens the related choices.
# A button that shows a choice and opens a list to change it: a chevron after the text, as wide as the text.
# It sets its size hint each time the text changes.
def chooser(widget: QPushButton, text: str, tip: str = "") -> None:
    widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    widget.setText(text)
    # Right to left puts the chevron after the name.
    widget.setIcon(icon(name="chevron_down"))
    widget.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    widget.setToolTip(tip or text)


# A thin vertical line that sets two groups of controls apart.
def separator(height: int = 22) -> QFrame:
    line = QFrame()
    line.setFixedSize(1, height)
    set_role(widget=line, role="separator")

    return line


def tool(action: QAction, role: str | None = None, menu: Iterable[QAction | None] = ()) -> QToolButton:
    entries = list(menu)
    widget = FitButton(room=TOOL_PADDING + (TOOL_ARROW if entries else 0))

    # An action with an icon shows only the icon here; menus show both.
    glyph = not action.icon().isNull()

    if glyph:
        widget.setIcon(action.icon())
        widget.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

    # Copied by hand: setDefaultAction kept the button at the width of its first text.
    def follow() -> None:
        widget.setText("" if glyph else action.iconText())
        widget.setToolTip(action.toolTip())
        # An icon means nothing to a screen reader, so it reads the full text.
        widget.setAccessibleName(action.text())
        widget.setEnabled(action.isEnabled())
        widget.updateGeometry()

    action.changed.connect(follow)
    follow()
    widget.clicked.connect(lambda _=False: action.trigger())

    if entries:
        widget.setMenu(fill_menu(menu=QMenu(widget), entries=entries))
        widget.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)

    if role:
        set_role(widget=widget, role=role)

    return widget


# A button that only opens a menu, such as the "more" icon for the less used actions.
def menu_button(text: str, entries: Iterable[QAction | None], tip: str = "", glyph: str = "") -> QToolButton:
    widget = QToolButton()
    widget.setText(text)

    if glyph:
        widget.setIcon(icon(name=glyph))
        widget.setIconSize(QSize(ICON_SIZE, ICON_SIZE))

    widget.setToolTip(tip)
    widget.setAccessibleName(tip or text)
    set_role(widget=widget, role="compact")
    widget.setMenu(fill_menu(menu=QMenu(widget), entries=entries))
    widget.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

    return widget


def row(*widgets: QWidget | None, spacing: int = 6, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QWidget:
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)

    for widget in widgets:
        if widget is None:
            layout.addStretch(1)
        else:
            layout.addWidget(widget)

    return holder


# A box shows nothing rather than its first entry when the saved choice is empty.
# Each item holds its value, shown as its label when labels has one; choice() reads the value back.
def fill_choices(box: QComboBox, choices: Iterable[str], current: str, labels: dict[str, str] | None = None) -> None:
    choices = list(choices)

    if current and current not in choices:
        choices.insert(0, current)

    box.blockSignals(True)
    box.clear()

    for value in choices:
        box.addItem((labels or {}).get(value, value), value)

    box.setCurrentIndex(choices.index(current) if current else -1)
    box.blockSignals(False)


def choice(box: QComboBox) -> str:
    value = box.currentData()

    return value if isinstance(value, str) else box.currentText()


def copy_text(text: str) -> None:
    QApplication.clipboard().setText(text)


# A bar with no range moves on its own, for work whose length is unknown.
def run_bar(bar: QProgressBar, loading: bool) -> None:
    if loading and bar.maximum():
        bar.setRange(0, 0)
    elif not loading and not bar.maximum():
        bar.setRange(0, 1000)
        bar.setValue(0)


# Esc in a search box clears it, the way search fields usually behave.
def clear_on_escape(box: QLineEdit) -> None:
    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), box)
    shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
    shortcut.activated.connect(box.clear)


def focus_box(box: QLineEdit) -> None:
    box.setFocus(Qt.FocusReason.ShortcutFocusReason)
    box.selectAll()
