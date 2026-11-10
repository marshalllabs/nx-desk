import threading
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

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

from ...schemas.artwork import ArtFiles, ArtStamp
from ...schemas.presentation import DownloadChoice
from ...schemas.snapshot import ModRow
from ..art import ART_SIZE
from ..cards.grid import CardGrid
from ..rows import SortState
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
    items: Dict[str, ModRow]
    shown_ids: Optional[List[str]]
    selected: Optional[str]
    picked: Set[str]
    list_sort: SortState
    chosen: List[str]
    missing: List[str]
    updates: List[str]
    # Downloaded and up to date, for Re-download all and Re-download selected.
    redo_all: List[str]
    redo_chosen: List[str]
    # What the two download buttons do now: their labels and the mods they take.
    download_choice: DownloadChoice
    redownload_choice: DownloadChoice
    download_action: QAction
    redownload_action: QAction
    detail_id: Optional[str]
    detail_key: Optional[Tuple[str, str]]
    art_id: Optional[str]
    # The banner of the shown game, drawn at twice ART_SIZE and scaled to the pane.
    art_image: Optional[QImage]
    art_cache: Dict[Tuple[str, str], Optional[QImage]]
    art_files: Dict[Tuple[str, str], ArtFiles]
    art_signature: Optional[ArtStamp]
    genres: List[str]
    selected_genres: Set[str]
    status_filter: Set[str]
    downloading: Set[str]
    reported_batch: int
    catalog_text: str
    active_catalog: Optional[str]
    shown_auto_repos: Optional[int]
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
    art_threads: List[threading.Thread]
    catalog_button: QPushButton
    refresh_action: QAction
    mode_actions: Dict[str, QAction]
    mode_button: QToolButton
    sort_actions: Dict[str, QAction]
    sort_direction_actions: Dict[bool, QAction]
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
    github_note: QLabel
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
    list_only: List[QWidget]
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
