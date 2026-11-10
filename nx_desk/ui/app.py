import queue
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QLoggingCategory, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from ..config import app_version
from ..schemas.presentation import UiCall
from ..schemas.update import AppUpdate, UpdateJob
from ..system import can_self_update, open_in_system, restart_program
from ..vault import Vault
from . import style
from .catalog_manager.manager import CatalogManager
from .catalog_tab.tab import CatalogTab
from .dialogs import ask_yes_no, run_dialog, show_message
from .homebrews_tab.tab import HomebrewsTab
from .notifier import Notifier
from .ports_tab.tab import PortsTab
from .settings_window import SettingsWindow
from .switch_sd.tab import SwitchSDTab
from .theme import SPACE
from .title_tab import TitleTab
from .upload_tab.tab import UploadTab
from .widgets.basics import button, label
from .widgets.spinner import Spinner

# The source is assets/icon.svg; packaged builds carry this file through --add-data.
ICON = Path(__file__).with_name(name="icon.png")


class App(QMainWindow):
    REFRESH = 400

    def __init__(self, vault: Vault) -> None:
        # Some art has a colour profile libpng finds odd; Qt reads the image anyway but prints a line for each one.
        # The line is not at the warning level, so the whole category is turned off, not only its warnings.
        QLoggingCategory.setFilterRules("qt.gui.imageio=false")
        # The one QApplication of the process, made here when nothing made it before.
        instance = QApplication.instance()

        if instance is None:
            instance = QApplication(sys.argv)

        if not isinstance(instance, QApplication):
            raise RuntimeError("The UI requires a QApplication")

        self.qt = instance
        self.qt.setApplicationName("NX Desk")
        QApplication.setWindowIcon(QIcon(str(ICON)))
        style.apply(app=self.qt, family=vault.font_family, size=vault.font_size)
        super().__init__()
        self.vault = vault
        self.notifier = Notifier(window=self, icon_path=ICON)
        self.manager: Optional[CatalogManager] = None
        self.app_update: Optional[AppUpdate] = None
        self.prompted_tag: Optional[str] = None
        self.closing = False
        # Work from other threads that must touch the UI waits here for the next repaint.
        self.pending: queue.Queue[UiCall] = queue.Queue()
        self.setWindowTitle(f"NX Desk {app_version()}")
        self.resize(1640, 900)
        # The Catalog tab's detail pane can shrink and its Genres column hides, so laptops fit too.
        self.setMinimumSize(1240, 640)
        self.build_menu()
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(SPACE["lg"], SPACE["sm"], SPACE["lg"], SPACE["sm"])
        layout.setSpacing(SPACE["sm"])
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.catalog = CatalogTab(app=self)
        self.uploads = UploadTab(app=self)
        self.ports = PortsTab(app=self)
        self.homebrews = HomebrewsTab(app=self)
        self.title_ids = TitleTab(app=self)
        self.switch_sd = SwitchSDTab(app=self)
        self.tabs.addTab(self.catalog, "Catalog")
        self.tabs.addTab(self.switch_sd, "Switch SD")
        self.tabs.addTab(self.ports, "Switch Ports")
        self.tabs.addTab(self.homebrews, "Homebrews")
        self.tabs.addTab(self.title_ids, "Title IDs")
        self.tabs.addTab(self.uploads, "GitHub")
        layout.addWidget(self.tabs, 1)
        foot = QHBoxLayout()
        # The footer reports the Catalog tab's state, so other tabs hide it but keep its space.
        self.footer = label(text="", role="muted")
        keep_space = self.footer.sizePolicy()
        keep_space.setRetainSizeWhenHidden(True)
        self.footer.setSizePolicy(keep_space)
        foot.addWidget(self.footer, 1)
        self.tabs.currentChanged.connect(lambda index: self.footer.setVisible(self.tabs.widget(index) is self.catalog))
        # Artwork tabs share this note, at the right of the footer, while SteamGridDB is asked.
        self.art_note = label(text="", role="muted")
        self.art_note.hide()
        self.art_spinner = Spinner(target=self.art_note)
        foot.addWidget(self.art_note)
        foot.addSpacing(10)
        self.app_update_button = button(text="", action=self.start_app_update, role="accent")
        self.app_update_button.hide()
        foot.addWidget(self.app_update_button)
        foot.addSpacing(10)
        foot.addWidget(label(text=app_version(), role="muted"))
        layout.addLayout(foot)
        self.setCentralWidget(central)

        # Ctrl+F (Cmd+F on macOS) goes to the search box of the tab in front.
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self).activated.connect(self.focus_search)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

        for keys, step in (("Ctrl+PgUp", -1), ("Alt+PgUp", -1), ("Ctrl+PgDown", 1), ("Alt+PgDown", 1)):
            QShortcut(QKeySequence(keys), self).activated.connect(lambda step=step: self.step_tab(step=step))

        self.timer = QTimer(self)
        self.timer.setInterval(self.REFRESH)
        self.timer.timeout.connect(self.refresh)
        self.refresh()
        self.timer.start()
        self.uploads.auto_load()
        self.ports.load()
        self.homebrews.load()
        self.title_ids.load()

    # One Settings window instead of a menu of submenus.
    def build_menu(self) -> None:
        settings = QAction("Settings", self)
        # The standard Preferences key has no binding on Linux desktops such as KDE; Qt reads Ctrl as Cmd on macOS.
        settings.setShortcut(QKeySequence("Ctrl+,"))
        settings.triggered.connect(self.open_settings)
        self.menuBar().addAction(settings)

    def open_settings(self) -> None:
        run_dialog(dialog=SettingsWindow(app=self))

    def set_font(self, family: str, size: int) -> None:
        self.vault.set_font(family=family, size=size)
        style.apply_font(app=self.qt, family=family, size=size)

    def units_changed(self, units: str) -> None:
        self.vault.set_size_units(units=units)
        self.uploads.repaint_sizes()
        self.catalog.detail_key = None
        self.catalog.model.cells = {}
        self.catalog.shown_ids = None

    def open_logs(self) -> None:
        self.vault.logs_dir.mkdir(exist_ok=True)
        open_in_system(path=self.vault.logs_dir)

    def focus_search(self) -> None:
        current = self.tabs.currentWidget()

        if isinstance(current, (CatalogTab, UploadTab, PortsTab, HomebrewsTab, TitleTab, SwitchSDTab)):
            current.focus_search()

    def step_tab(self, step: int) -> None:
        self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    # New mods and finished runs, for when the window is not in front.
    def notify(self, title: str, text: str) -> None:
        if self.vault.notify and text:
            self.notifier.show(title=title, text=text)

    def later(self, action: Callable[..., object], *args: object) -> None:
        self.pending.put(item=UiCall(action=action, args=args))

    def set_footer(self, text: str, error: bool = False) -> None:
        self.footer.setText(text)
        style.set_role(widget=self.footer, role="error" if error else "muted")

    def open_manager(self) -> None:
        if self.manager is None:
            self.manager = CatalogManager(app=self)

        self.manager.prepare()
        self.manager.show()
        self.manager.raise_()
        self.manager.activateWindow()

    def refresh(self) -> None:
        snapshot = self.vault.snapshot()
        github = self.vault.upload_snapshot()
        self.catalog.refresh(snapshot=snapshot, github=github)
        self.uploads.paint(job=github)
        self.ports.paint(job=self.vault.port_snapshot())
        self.homebrews.paint(job=self.vault.homebrew_snapshot())
        self.title_ids.paint(job=self.vault.title_snapshot())
        self.switch_sd.paint(job=self.vault.switch_snapshot())
        self.paint_app_update(update=snapshot.app_update, job=snapshot.app_update_job)
        self.paint_art_note()

        for notice in self.vault.take_notices():
            self.notifier.show(title=notice.title, text=notice.text)

        # Popups run their own loop, so the queue is drained after the repaint and one at a time.
        try:
            pending = self.pending.get_nowait()
            action, args = pending.action, pending.args

        except queue.Empty:
            return

        QTimer.singleShot(0, lambda: action(*args))

    def paint_art_note(self) -> None:
        if self.vault.art_busy():
            self.art_note.show()
            self.art_spinner.start(text="Fetching artwork from SteamGridDB…")

        else:
            self.art_spinner.stop()
            self.art_note.hide()

    def paint_app_update(self, update: Optional[AppUpdate], job: Optional[UpdateJob]) -> None:
        self.app_update = update

        if not update:
            return

        phase = job.phase if job else None

        if phase == "done":
            restart_program()
            self.closing = True
            self.qt.quit()

            return

        if job and phase == "error":
            self.vault.app_update_job = None
            self.later(self.report_update_error, job.message)

        if job and phase == "downloading":
            text = f"Updating {100 * job.done // max(1, (job.total or 1))}%"

        elif phase == "installing":
            text = "Installing update"

        else:
            text = f"New version {update.tag}"

        self.app_update_button.setText(text)
        self.app_update_button.setEnabled(phase not in ("downloading", "installing"))
        self.app_update_button.show()

        if update.tag != self.prompted_tag:
            self.prompted_tag = update.tag
            self.later(action=self.prompt_app_update)

    def prompt_app_update(self) -> None:
        update = self.app_update

        if update is None:
            return

        action = (
            "Download and update now? The app will restart."
            if can_self_update(update=update)
            else "Open the download page to update?"
        )

        if ask_yes_no(
            title="New version",
            message=f"NX Desk {update.tag} is out. {action}",
            parent=self,
            action="Update" if can_self_update(update=update) else "Open page",
            keep="Later",
        ):
            self.start_app_update()

    def start_app_update(self) -> None:
        update = self.app_update

        if update is None:
            return

        if self.vault.switch_snapshot().phase != "idle":
            show_message(
                title="Switch SD",
                message="Wait for the card operation to finish before updating the app.",
                parent=self,
            )

            return

        if not can_self_update(update=update):
            open_in_system(path=update.url)

        elif any(job.phase != "error" for job in self.vault.snapshot_jobs()):
            show_message(
                title="Downloading",
                message="Wait for downloads to finish before updating the app.",
                parent=self,
            )

        else:
            self.vault.set_update_job(phase="queued", done=0, total=1)
            threading.Thread(target=self.vault.install_app_update, args=(update,), daemon=True).start()

    def report_update_error(self, message: str) -> None:
        text = f"Could not update: {message}\n\nOpen the download page to update manually?"

        if (
            ask_yes_no(title="Update error", message=text, parent=self, action="Open page", keep="Close")
            and self.app_update
        ):
            open_in_system(path=self.app_update.url)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.closing:
            event.accept()

            return

        if self.vault.switch_snapshot().phase != "idle":
            show_message(title="Switch SD", message="Finish or cancel the card operation before quitting.", parent=self)
            event.ignore()

            return

        downloading = any(job.phase != "error" for job in self.vault.snapshot_jobs())
        active = downloading or bool(self.vault.app_update_job)

        if active and not ask_yes_no(
            title="Downloading",
            message="Downloads or uploads are still running. Quit now? Downloads resume next time; saved mods stay on disk.",
            parent=self,
            action="Quit",
            danger=True,
            keep="Keep running",
        ):
            event.ignore()

            return

        if self.vault.changing_github() and not ask_yes_no(
            title="GitHub",
            message="Still working on GitHub. Quit now? Files not sent yet stay as they were.",
            parent=self,
            action="Quit",
            danger=True,
            keep="Keep running",
        ):
            event.ignore()

            return

        event.accept()

    def run(self) -> None:
        self.showMaximized()
        self.qt.exec()
