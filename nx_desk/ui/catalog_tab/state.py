import threading
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QImage
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableView,
    QTextBrowser,
    QToolButton,
    QWidget,
)

from ...schemas.snapshot import ModRow
from ..art import ART_SIZE
from ..cards.grid import CardGrid
from ..rows import Choice, SortState
from ..widgets.choice_popup import ChoicePopup
from ..widgets.click_label import ClickLabel
from ..widgets.log_pane import LogPane
from ..widgets.spinner import Spinner
from ..widgets.view_switch import ViewSwitch
from .game_model import GameModel

if TYPE_CHECKING:
    from ...vault import Vault
    from ..app import App


# The attributes CatalogTab builds, for the mixins that share them.
class CatalogTabState(QWidget):
    ART_SIZE = ART_SIZE
    DETAIL_WIDTH = 440

    app: "App"
    vault: "Vault"
    items: dict[str, ModRow]
    shown_ids: list[str] | None
    selected: str | None
    picked: set[str]
    list_sort: SortState
    chosen: list[str]
    missing: list[str]
    updates: list[str]
    # Downloaded and up to date, for Re-download all and Re-download selected.
    redo_all: list[str]
    redo_chosen: list[str]
    # What the two download buttons do now: their labels and the mods they take.
    download_choice: Choice
    redownload_choice: Choice
    download_action: QAction
    redownload_action: QAction
    detail_id: str | None
    detail_key: tuple[str, str] | None
    art_id: str | None
    # The banner of the shown game, drawn at twice ART_SIZE and scaled to the pane.
    art_image: QImage | None
    art_cache: dict[tuple[str, str], QImage | None]
    art_files: dict[tuple[str, str], tuple[Path | None, Path | None]]
    art_signature: tuple[object, ...] | None
    genres: list[str]
    selected_genres: set[str]
    status_filter: set[str]
    downloading: set[str]
    reported_batch: int
    catalog_text: str
    active_catalog: str | None
    shown_auto_repos: int | None
    restoring: bool
    views: QStackedWidget
    log: LogPane
    view_switch: ViewSwitch
    # "list" or "grid": how the games show when the Log is not in front.
    mode: str
    body_stack: QStackedWidget
    grid: CardGrid
    grid_empty: QLabel
    sort_button: QToolButton
    art_threads: list[threading.Thread]
    catalog_button: QPushButton
    refresh_action: QAction
    mode_actions: dict[str, QAction]
    mode_button: QToolButton
    sort_actions: dict[str, QAction]
    sort_direction_actions: dict[bool, QAction]
    summary: QLabel
    summary_spinner: Spinner
    new_label: ClickLabel
    update_label: ClickLabel
    download_entry: QLineEdit
    download_button: QPushButton
    move_button: QPushButton
    open_button: QPushButton
    mod_entry: QLineEdit
    auto_upload_box: QCheckBox
    gh_note: QLabel
    auto_repo_button: QPushButton
    auto_delete_box: QCheckBox
    get_button: QToolButton
    redo_button: QToolButton
    update_all_button: QPushButton
    stop_button: QPushButton
    search: QLineEdit
    genre_button: QPushButton
    genre_popup: ChoicePopup
    status_button: QPushButton
    status_popup: ChoicePopup
    list_only: list[QWidget]
    overall_row: QWidget
    overall_label: QLabel
    overall_bar: QProgressBar
    model: GameModel
    table: QTableView
    list_empty: QLabel
    detail: QStackedWidget
    detail_scroll: QScrollArea
    art: QLabel
    name: QLabel
    state_label: QLabel
    progress: QProgressBar
    action: QPushButton
    text: QTextBrowser
