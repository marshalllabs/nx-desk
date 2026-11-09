from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from ...schemas.github import RetryState
from ...schemas.presentation import CompareStamp, UploadPaintStamp
from ..layout_models import LegendNote
from ..widgets.log_pane import LogPane
from ..widgets.spinner import Spinner
from ..widgets.view_switch import ViewSwitch

if TYPE_CHECKING:
    from ...vault import Vault
    from ..app import App


# The attributes UploadTab builds, for the mixins that share them.
class UploadTabState(QWidget):
    app: "App"
    vault: "Vault"
    painted: Optional[UploadPaintStamp]
    shown_tree: Optional[int]
    shown_releases: Optional[int]
    shown_repos: Optional[int]
    shown_assets: Optional[Tuple[int, int]]
    shown_source: Optional[int]
    reported_runs: int
    reported_alerts: int
    asset_groups: Dict[str, List[str]]
    known_releases: List[str]
    legend: Dict[str, LegendNote]
    unit_of: Dict[str, str]
    unit_iid: Dict[str, str]
    rows: Dict[str, QTreeWidgetItem]
    asset_rows: Dict[str, QTreeWidgetItem]
    asset_sizes: Dict[str, int]
    asset_updated: Dict[str, str]
    known_groups: Set[str]
    # Kind, names and release of what failed last, which Retry and Retry all run again.
    retry_job: RetryState
    shown_compare: Optional[CompareStamp]
    compare_titles: List[QLabel]
    compare_notes: List[Dict[str, QLabel]]
    compare_trees: List[QTreeWidget]
    bodies: QStackedWidget
    compare_box: QComboBox
    compare_button: QPushButton
    release_menu: QToolButton
    failed_label: QLabel
    # One action each, shared by buttons, ▾ menus and right-click menus.
    scan_action: QAction
    refresh_action: QAction
    recompare_action: QAction
    upload_action: QAction
    upload_all_action: QAction
    upload_delete_action: QAction
    delete_folders_action: QAction
    download_action: QAction
    download_all_action: QAction
    delete_assets_action: QAction
    retry_action: QAction
    retry_all_action: QAction
    create_action: QAction
    rename_action: QAction
    delete_release_action: QAction
    retry_button: QToolButton
    delete_source_button: QToolButton
    views: QStackedWidget
    log: LogPane
    view_switch: ViewSwitch
    source: QLineEdit
    repo_button: QPushButton
    # The chosen repository as owner/name, the latest release, and the release compared with.
    repo: str
    latest_release: str
    compared: str
    release_box: QComboBox
    scan_button: QToolButton
    upload_button: QToolButton
    cancel_button: QPushButton
    delete_button: QToolButton
    download_button: QToolButton
    refresh_button: QToolButton
    progress_row: QWidget
    progress_label: QLabel
    spinner: Spinner
    progress: QProgressBar
    status: QLabel
    source_title: QLabel
    release_title: QLabel
    tree: QTreeWidget
    source_search: QLineEdit
    release_search: QLineEdit
    assets: QTreeWidget
