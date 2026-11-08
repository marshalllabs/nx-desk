import html
from collections.abc import Iterable, Sequence

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..utils.text import plural
from .widgets.basics import button, label

# Past this many rows the table scrolls instead of growing the window.
TABLE_LINES = 10
TABLE_ROW = 28
RIGHT = ("Size",)
# The column names, the rows of texts and a total shown under the table.
Table = tuple[Sequence[str], Sequence[Sequence[str]], str]


__all__ = ["ask_text", "ask_yes_no", "confirm", "confirm_typed", "plural", "show_message"]


# A finished dialog is deleted at once. Left under the window, it crashed Python on exit.
def run_dialog(dialog: QDialog) -> int:
    result = dialog.exec()
    shiboken6.delete(dialog)

    return result


# A wrapped label told its layout a height for another width than it got, so a fixed-size dialog cut
# off its lines. It gets one width, its text's up to high, and the height that width needs.
def fit_text(widget: QLabel, low: int, high: int) -> None:
    widest = max(widget.fontMetrics().horizontalAdvance(line) for line in widget.text().split("\n"))
    width = min(high, max(low, widest + 8))
    widget.setFixedWidth(width)
    widget.setFixedHeight(widget.heightForWidth(width))


# Qt places a dialog over the middle of its parent and keeps it on the screen.
# The first button is the action, in the accent or, for one that stops or removes something, in red.
def popup(
    title: str,
    message: str,
    parent: QWidget | None,
    buttons: Sequence[str],
    table: Table | None = None,
    role: str = "accent",
) -> int:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 22, 28, 18)
    layout.setSpacing(12)
    text = label(text=message)
    text.setWordWrap(True)
    text.setAlignment(Qt.AlignmentFlag.AlignCenter)
    fit_text(widget=text, low=240, high=640 if table else 460)
    layout.addWidget(text, alignment=Qt.AlignmentFlag.AlignCenter)

    if table:
        columns, rows, total = table
        layout.addWidget(detail_table(columns=columns, rows=rows, parent=parent))

        if total:
            layout.addWidget(label(text=total, role="muted"), alignment=Qt.AlignmentFlag.AlignRight)

    chosen = [len(buttons) - 1]

    def pick(value: int) -> None:
        chosen[0] = value
        dialog.accept()

    row = QHBoxLayout()
    row.addStretch(1)

    for index, text_value in enumerate(buttons):
        choice = button(text=text_value, role=None if index else role)
        choice.setMinimumWidth(96)
        choice.clicked.connect(lambda _=False, value=index: pick(value=value))

        if index == 0:
            choice.setDefault(True)

        row.addWidget(choice)

    row.addStretch(1)
    layout.addLayout(row)
    dialog.setFixedSize(dialog.sizeHint())
    run_dialog(dialog=dialog)

    return chosen[0]


# Like GitHub: an action that cannot be undone waits until its word is typed, so a stray click or
# Enter cannot run it.
def confirm_typed(
    title: str,
    message: str,
    word: str,
    action: str,
    parent: QWidget | None,
    table: Table | None = None,
) -> bool:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 22, 28, 18)
    layout.setSpacing(12)
    text = label(text=message)
    text.setWordWrap(True)
    fit_text(widget=text, low=420, high=640 if table else 480)
    layout.addWidget(text)

    if table:
        columns, rows, total = table
        layout.addWidget(detail_table(columns=columns, rows=rows, parent=parent))

        if total:
            layout.addWidget(label(text=total, role="muted"), alignment=Qt.AlignmentFlag.AlignRight)

    layout.addWidget(label(text=f"To confirm, type <b>{html.escape(word)}</b> below."))
    entry = QLineEdit()
    entry.setPlaceholderText(word)
    layout.addWidget(entry)
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(button(text="Cancel", action=dialog.reject))
    go = button(text=action, action=dialog.accept, role="danger")
    go.setEnabled(False)
    row.addWidget(go)
    layout.addLayout(row)

    def submitted() -> None:
        if go.isEnabled():
            dialog.accept()

    entry.textChanged.connect(lambda typed: go.setEnabled(typed == word))
    entry.returnPressed.connect(submitted)
    entry.setFocus()
    dialog.setFixedSize(dialog.sizeHint())

    return run_dialog(dialog=dialog) == QDialog.DialogCode.Accepted


def detail_table(columns: Sequence[str], rows: Sequence[Sequence[str]], parent: QWidget | None) -> QTableWidget:
    table = QTableWidget(len(rows), len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(TABLE_ROW)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    for row, texts in enumerate(rows):
        for column, text in enumerate(texts):
            cell = QTableWidgetItem(text)

            if columns[column] in RIGHT:
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            table.setItem(row, column, cell)

    for column, name in enumerate(columns):
        if name in RIGHT:
            table.horizontalHeaderItem(column).setTextAlignment(  # type: ignore[union-attr]
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )

    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.resizeColumnsToContents()
    widths = [header.sectionSize(column) + 24 for column in range(len(columns))]
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    frame = 2 * table.frameWidth()
    scroll = table.verticalScrollBar().sizeHint().width() if len(rows) > TABLE_LINES else 0
    screen = (parent.screen() if parent else table.screen()).availableGeometry()
    table.setFixedWidth(min(sum(widths) + frame + scroll, int(screen.width() * 0.7)))
    table.setFixedHeight(header.sizeHint().height() + TABLE_ROW * min(len(rows), TABLE_LINES) + frame)

    return table


def show_message(title: str, message: str, parent: QWidget | None) -> None:
    popup(title=title, message=message, parent=parent, buttons=("OK",))


# Buttons say what they do, such as "Stop" and "Cancel", so the answer does not depend on reading
# the question twice. Without an action they stay Yes and No.
def ask_yes_no(
    title: str,
    message: str,
    parent: QWidget | None,
    action: str = "",
    danger: bool = False,
    keep: str = "Cancel",
) -> bool:
    # keep names the other way out, such as "Keep running" when the action itself stops something.
    buttons = (action, keep) if action else ("Yes", "No")

    return (
        popup(title=title, message=message, parent=parent, buttons=buttons, role="danger" if danger else "accent") == 0
    )


# Asks before an action on several things and lists each one with its details, so the user sees
# what is affected. Rows are tuples of texts matching columns; columns named in RIGHT are right-aligned.
def confirm(
    title: str,
    question: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[str]],
    parent: QWidget | None,
    total: str = "",
) -> bool:
    rows = list(rows)
    # One row already shows its own size.
    total = total if len(rows) > 1 else ""

    return (
        bool(rows)
        # The title names the action, such as "Re-download" or "Upload all", so it is the button too.
        and popup(title=title, message=question, parent=parent, buttons=(title, "Cancel"), table=(columns, rows, total))
        == 0
    )


def ask_text(title: str, message: str, initial: str, parent: QWidget | None) -> str | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(28, 22, 28, 18)
    layout.setSpacing(12)
    text = label(text=message)
    text.setWordWrap(True)
    text.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(text)
    entry = QLineEdit(initial)
    entry.setMinimumWidth(340)
    entry.selectAll()
    layout.addWidget(entry)
    row = QHBoxLayout()
    row.addStretch(1)
    ok = button(text="OK", action=dialog.accept, role="accent")
    ok.setDefault(True)
    row.addWidget(ok)
    row.addWidget(button(text="Cancel", action=dialog.reject))
    row.addStretch(1)
    layout.addLayout(row)
    entry.returnPressed.connect(dialog.accept)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    value = entry.text().strip()
    shiboken6.delete(dialog)

    return value if accepted else None
