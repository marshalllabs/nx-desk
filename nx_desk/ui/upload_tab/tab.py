from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..icon_set import icon
from ..repo_picker import pick_repo, show_repo
from ..theme import COLORS, SPACE
from ..widgets.basics import button, clear_on_escape, fill_choices, focus_box, label, menu_button, tool
from ..widgets.log_pane import LogPane
from ..widgets.spinner import Spinner
from ..widgets.view_switch import ViewSwitch
from .painting import Painting
from .transfers import Transfers
from .tree_items import filter_tree, make_tree

if TYPE_CHECKING:
    from ..app import App


class UploadTab(Transfers, Painting):
    def __init__(self, app: "App") -> None:
        super().__init__()
        self.app = app
        self.vault = app.vault
        # What each part of the tab last painted, so a repaint only touches what changed.
        self.painted: tuple[object, ...] | None = None
        self.shown_tree: int | None = None
        self.shown_releases: int | None = None
        self.shown_repos: int | None = None
        self.shown_assets: tuple[int, int] | None = None
        self.shown_source: int | None = None
        self.reported_runs = 0
        self.reported_alerts = 0
        # Release file group -> the file names in it.
        self.asset_groups: dict[str, list[str]] = {}
        self.known_releases: list[str] = []
        self.legend: dict[str, tuple[QLabel, str]] = {}
        # Tree row id -> mod folder name, and back.
        self.unit_of: dict[str, str] = {}
        self.unit_iid: dict[str, str] = {}
        self.rows: dict[str, QTreeWidgetItem] = {}
        self.asset_rows: dict[str, QTreeWidgetItem] = {}
        self.asset_sizes: dict[str, int] = {}
        self.asset_updated: dict[str, str] = {}
        self.known_groups: set[str] = set()
        self.retry_job: tuple[str, list[str], str] = ("", [], "")
        self.shown_compare: tuple[int, int, str] | None = None
        self.compare_titles: list[QLabel] = []
        self.compare_notes: list[dict[str, QLabel]] = []
        self.compare_trees: list[QTreeWidget] = []
        self.repo = self.vault.upload_repo
        self.latest_release = ""
        self.compared = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        self.build_actions()
        layout.addLayout(self.build_settings())
        layout.addLayout(self.build_progress())
        # The tabs of the views sit right under the frames, at the left, over the source panel.
        self.view_switch = ViewSwitch(swap=self.show_view, bottom=0)
        layout.addWidget(self.view_switch, 0, Qt.AlignmentFlag.AlignLeft)
        self.views = QStackedWidget()
        # The source folders and the release, or two releases while comparing them.
        self.bodies = QStackedWidget()
        self.bodies.addWidget(self.build_body())
        self.bodies.addWidget(self.build_compare_body())
        self.views.addWidget(self.bodies)
        self.log = LogPane()
        self.views.addWidget(self.log)
        layout.addWidget(self.views, 1)
        self.view_switch.show_view(view="list")

    def make_action(self, text: str, slot: Callable[[], object], tip: str = "", glyph: str = "") -> QAction:
        action = QAction(text, self)
        action.triggered.connect(lambda _=False: slot())

        if tip:
            action.setToolTip(tip)

        # An icon, such as refresh, shows alone on its button while menus keep the full text too.
        if glyph:
            action.setIcon(icon(name=glyph))

        return action

    # Every action is one QAction, shared by its button, its ▾ menu and the right-click menus, so
    # paint_choice sets each text and state once.
    def build_actions(self) -> None:
        self.scan_action = self.make_action(text="Scan the source folder", slot=self.scan, glyph="refresh")
        self.refresh_action = self.make_action(text="Reload the release", slot=self.refresh, glyph="refresh")
        self.recompare_action = self.make_action(
            text="Reload the compared release",
            slot=self.start_compare,
            glyph="refresh",
        )
        self.upload_action = self.make_action(text="Upload", slot=self.upload, tip="Upload the chosen folders")
        self.upload_all_action = self.make_action(text="Upload all", slot=self.upload_all)
        self.upload_delete_action = QAction("Delete after upload", self, checkable=True)
        self.upload_delete_action.setToolTip("Delete each source folder once it is on the release and recorded")
        self.upload_delete_action.setChecked(self.vault.upload_delete)
        self.upload_delete_action.toggled.connect(lambda enabled: self.vault.set_upload_delete(enabled=enabled))
        self.delete_folders_action = self.make_action(
            text="Delete",
            slot=self.delete_folders,
            tip="Delete the chosen folders from disk",
        )
        self.download_action = self.make_action(text="Download", slot=self.download, tip="Download the chosen files")
        self.download_all_action = self.make_action(text="Download all", slot=self.download_all)
        self.delete_assets_action = self.make_action(
            text="Delete",
            slot=self.delete,
            tip="Delete the chosen files from the release",
        )
        self.retry_action = self.make_action(text="Retry chosen", slot=self.retry)
        self.retry_all_action = self.make_action(text="Retry all", slot=self.retry_all)
        self.create_action = self.make_action(text="Create release…", slot=self.create_release)
        self.rename_action = self.make_action(text="Rename release…", slot=self.edit_release)
        self.delete_release_action = self.make_action(text="Delete release…", slot=self.delete_release)

    # Two frames over the two panels, like the Catalog tab's: the source folder over the source panel, and the
    # GitHub choices (the repository, the release and the one it is compared with) over the release panel. The
    # spacing and stretch match build_body, so each frame lines up with its panel.
    def build_settings(self) -> QGridLayout:
        halves = QGridLayout()
        halves.setHorizontalSpacing(12)
        halves.setColumnStretch(0, 1)
        halves.setColumnStretch(1, 1)
        place = QGroupBox("Source folder")
        source = QHBoxLayout(place)
        source.setSpacing(6)
        self.source = QLineEdit(self.vault.upload_source)
        self.source.textChanged.connect(lambda _: self.save())
        self.source.textChanged.connect(self.source.setToolTip)
        self.source.setToolTip(self.vault.upload_source)
        self.source.setPlaceholderText("The folder that holds your mod folders")
        self.source.setCursorPosition(0)
        source.addWidget(self.source, 1)
        source.addWidget(button(text="Choose…", action=self.browse))
        halves.addWidget(place, 0, 0)
        # A popup lists the repositories with their owners, and reloads them there.
        self.repo_button = button(text="", action=self.choose_repo, role="field")
        show_repo(widget=self.repo_button, repo=self.repo, repos=[])
        self.release_box = QComboBox()
        fill_choices(box=self.release_box, choices=[], current=self.vault.upload_tag)
        self.release_box.activated.connect(self.release_chosen)
        self.release_menu = menu_button(
            text="",
            glyph="more",
            entries=(self.create_action, self.rename_action, None, self.delete_release_action),
            tip="Create, rename or delete a release",
        )
        # Compare sits before its release, so the row reads "Compare <release>". While comparing it is lit
        # and reads Stop.
        self.compare_button = button(text="Compare", action=self.toggle_compare)
        self.compare_button.setCheckable(True)
        self.compare_box = QComboBox()
        self.compare_box.activated.connect(self.compare_chosen)
        hub = QGroupBox("GitHub")
        github = QHBoxLayout(hub)
        github.setSpacing(6)

        for box in (self.release_box, self.compare_box):
            # Long names would otherwise widen this half past its panel; the list and the tooltip
            # still show them whole.
            box.setMinimumContentsLength(12)
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            box.currentTextChanged.connect(box.setToolTip)

        github.addWidget(label(text="Repository", role="muted"))
        github.addWidget(self.repo_button)
        github.addSpacing(12)
        github.addWidget(label(text="Release", role="muted"))
        github.addWidget(self.release_box, 3)
        github.addWidget(self.release_menu)
        github.addSpacing(12)
        github.addWidget(self.compare_button)
        github.addWidget(self.compare_box, 2)
        halves.addWidget(hub, 0, 1)

        return halves

    def choose_repo(self) -> None:
        if self.vault.uploading():
            return

        picked = pick_repo(parent=self.app, vault=self.vault, current=self.repo)

        if picked and picked != self.repo:
            self.repo = picked
            show_repo(widget=self.repo_button, repo=self.repo, repos=self.vault.upload_snapshot().repos)
            self.save()
            self.load()

    def release_chosen(self, _index: int) -> None:
        self.save()
        self.fill_compare_box()

        # The release compared with cannot also be the chosen one.
        if self.comparing and self.tag == self.compared:
            self.stop_compare()

        self.paint_choice()
        self.run(action=self.vault.load_assets)

    def build_progress(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(6)
        # The row shows only while a job runs, and takes no room otherwise.
        self.progress_row = QWidget()
        overall = QHBoxLayout(self.progress_row)
        overall.setContentsMargins(0, 0, 0, 0)
        overall.setSpacing(10)
        self.progress_label = label(text="", role="muted")
        self.progress_label.setFixedWidth(520)
        self.spinner = Spinner(target=self.progress_label)
        overall.addWidget(self.progress_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        overall.addWidget(self.progress, 1)
        self.progress_row.hide()
        column.addWidget(self.progress_row)
        # Errors share a line with Retry after a failure and Cancel while a job runs.
        line = QHBoxLayout()
        line.setSpacing(6)
        self.status = label(text="", role="muted")
        self.status.setWordWrap(True)
        self.status.hide()
        line.addWidget(self.status, 1)
        self.failed_label = label(text="", role="error")
        self.retry_button = tool(action=self.retry_all_action, menu=(self.retry_action,))
        self.cancel_button = button(text="Cancel", action=self.cancel, role="danger")

        for widget in (self.failed_label, self.retry_button, self.cancel_button):
            widget.hide()
            line.addWidget(widget)

        column.addLayout(line)

        return column

    def build_body(self) -> QWidget:
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(2, 1)
        self.scan_button = tool(action=self.scan_action)
        self.upload_button = tool(
            action=self.upload_action,
            role="accent",
            menu=(self.upload_all_action, None, self.upload_delete_action),
        )
        self.delete_source_button = tool(action=self.delete_folders_action, role="danger")
        self.source_title = label(text="Local mods (0)", role="name")
        source_head, source_notes = self.panel_title(
            title=self.source_title,
            tools=(self.scan_button, self.upload_button, self.delete_source_button),
            legend=(
                ("uploaded", "Uploaded", "ok"),
                ("missing", "Not uploaded", "muted"),
                ("invalid", "Invalid", "bad"),
            ),
        )
        grid.addLayout(source_head, 0, 0)
        self.refresh_button = tool(action=self.refresh_action)
        # The primary action of the release panel, styled like Upload and the Catalog tab's Download.
        self.download_button = tool(action=self.download_action, role="accent", menu=(self.download_all_action,))
        self.delete_button = tool(action=self.delete_assets_action, role="danger")
        self.release_title = label(text="Release mods (0)", role="name")
        release_head, release_notes = self.panel_title(
            title=self.release_title,
            tools=(self.refresh_button, self.download_button, self.delete_button),
            legend=(("local", "Downloaded", "ok"), ("orphan", "Not downloaded", "miss")),
        )
        grid.addLayout(release_head, 0, 1)
        self.tree = make_tree(titles=("Folder", "Size", "Status"))
        self.assets = make_tree(titles=("File", "Size", "Updated", "Status"))
        self.assets.header().resizeSection(2, 110)
        self.source_search = self.search_box(placeholder="Search folders", tree=self.tree)
        self.release_search = self.search_box(placeholder="Search files", tree=self.assets)
        # The counts sit beside the search box, which keeps each panel's toolbar narrow.
        source_notes.insertWidget(0, self.source_search, 1)
        release_notes.insertWidget(0, self.release_search, 1)
        grid.addLayout(source_notes, 1, 0)
        grid.addLayout(release_notes, 1, 1)
        grid.addWidget(self.tree, 2, 0)
        grid.addWidget(self.assets, 2, 1)
        # Like the Catalog list: a double-click on a mod folder uploads it, on a release file downloads it.
        self.tree.itemDoubleClicked.connect(lambda item, _: self.upload_row(item=item))
        self.assets.itemDoubleClicked.connect(lambda item, _: self.download_row(item=item))
        self.tree.itemSelectionChanged.connect(self.paint_choice)
        self.assets.itemSelectionChanged.connect(self.paint_choice)
        self.attach_menu(
            tree=self.tree,
            entries=(
                self.upload_action,
                self.retry_action,
                self.delete_folders_action,
                None,
                self.upload_all_action,
                self.scan_action,
            ),
        )
        self.attach_menu(
            tree=self.assets,
            entries=(
                self.download_action,
                self.retry_action,
                self.delete_assets_action,
                None,
                self.download_all_action,
                self.refresh_action,
            ),
        )

        return body

    def search_box(self, placeholder: str, tree: QTreeWidget) -> QLineEdit:
        box = QLineEdit()
        box.setPlaceholderText(placeholder)
        box.setClearButtonEnabled(True)
        box.setToolTip("Ctrl+F to search, Esc to clear")
        clear_on_escape(box=box)

        def search(text: str) -> None:
            filter_tree(tree=tree, text=text)
            # Hidden rows lose their selection, so the button counts change too.
            self.paint_choice()

        box.textChanged.connect(search)

        return box

    # The panel's name, its buttons, then the legend of its colors.
    def panel_title(
        self,
        title: QLabel,
        tools: Iterable[QWidget],
        legend: Iterable[tuple[str, str, str]],
    ) -> tuple[QHBoxLayout, QHBoxLayout]:
        head = QHBoxLayout()
        head.setSpacing(SPACE["sm"])
        head.addWidget(title)
        head.addSpacing(SPACE["xs"])

        for widget in tools:
            head.addWidget(widget)

        head.addStretch(1)
        notes = QHBoxLayout()
        notes.setSpacing(SPACE["md"])

        for key, text, color in legend:
            note = label(text=text)
            note.setStyleSheet(f"color: {COLORS[color]};")
            notes.addWidget(note)
            self.legend[key] = (note, text)

        return head, notes

    # Ctrl+F goes to the release files' search when that panel has focus, else to the folders'.
    def focus_search(self) -> None:
        self.view_switch.show_view(view="list")
        focus_box(box=self.release_search if self.assets.hasFocus() else self.source_search)

    def show_view(self, view: str) -> None:
        self.views.setCurrentIndex(1 if view == "log" else 0)

        if view == "log":
            self.log.show_latest()
