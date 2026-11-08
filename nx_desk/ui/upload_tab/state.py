from typing import TYPE_CHECKING

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

from ..widgets.log_pane import LogPane
from ..widgets.spinner import Spinner
from ..widgets.view_switch import ViewSwitch

if TYPE_CHECKING:
    from ...vault import Vault
    from ..app import App


# The attributes UploadTab builds, for the mixins that share them.
class UploadTabState(QWidget):
    app: App
    vault: Vault
    painted: tuple[object, ...] | None
    shown_tree: int | None
    shown_releases: int | None
    shown_repos: int | None
    shown_assets: tuple[int, int] | None
    shown_source: int | None
    reported_runs: int
    reported_alerts: int
    asset_groups: dict[str, list[str]]
    known_releases: list[str]
    legend: dict[str, tuple[QLabel, str]]
    unit_of: dict[str, str]
    unit_iid: dict[str, str]
    rows: dict[str, QTreeWidgetItem]
    asset_rows: dict[str, QTreeWidgetItem]
    asset_sizes: dict[str, int]
    asset_updated: dict[str, str]
    known_groups: set[str]
    # Kind, names and release of what failed last, which Retry and Retry all run again.
    retry_job: tuple[str, list[str], str]
    shown_compare: tuple[int, int, str] | None
    compare_titles: list[QLabel]
    compare_notes: list[dict[str, QLabel]]
    compare_trees: list[QTreeWidget]
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
