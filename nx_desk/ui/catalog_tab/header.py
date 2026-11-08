import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QLabel,
    QWidget,
)

from ...schemas.download import BatchProgress
from ...schemas.github import UploadSnapshot
from ...schemas.snapshot import Snapshot
from ...utils.text import plural
from ..dialogs import show_message
from ..repo_picker import pick_repo, show_repo
from ..rows import action_text
from ..widgets.basics import chooser, run_bar
from .actions import Actions
from .game_list import GameList


class Header(GameList, Actions):
    def auto_upload_changed(self, enabled: bool) -> None:
        self.vault.set_auto_upload(enabled=enabled)

        # Deleting needs the upload, so the second box follows the first.
        if not enabled:
            self.auto_delete_box.setChecked(False)

    def auto_delete_changed(self, enabled: bool) -> None:
        self.vault.set_auto_delete(enabled=enabled)

        if self.vault.auto_delete:
            threading.Thread(target=self.vault.refresh_release_state, daemon=True).start()

    def choose_auto_repo(self) -> None:
        picked = pick_repo(parent=self.app, vault=self.vault, current=self.vault.auto_repo)

        if picked and picked != self.vault.auto_repo:
            self.vault.set_auto_repo(repo=picked)
            show_repo(widget=self.auto_repo_button, repo=picked, repos=self.vault.upload_snapshot().repos)
            threading.Thread(target=self.vault.refresh_release_state, daemon=True).start()

    # These boxes work from what gh reports, so they wait for its first answer.
    def paint_auto_upload(self, github: UploadSnapshot) -> None:
        ready = github.gh_ready

        if github.repo_list != self.shown_auto_repos:
            self.shown_auto_repos = github.repo_list
            show_repo(widget=self.auto_repo_button, repo=self.vault.auto_repo, repos=github.repos)

        self.auto_upload_box.setEnabled(bool(ready))
        chosen = bool(ready) and self.auto_upload_box.isChecked()
        self.auto_repo_button.setEnabled(chosen)
        self.auto_delete_box.setEnabled(chosen)
        # A disabled box says why, so it does not look broken.
        self.auto_delete_box.setToolTip(
            "Delete each mod from disk once it is on GitHub"
            if chosen
            else "Turn on Upload to GitHub first; a local copy is only deleted after its upload",
        )
        self.gh_note.setVisible(ready is False)

    def paint_overall(self, batch: BatchProgress, checking: bool = False) -> None:
        run_bar(bar=self.overall_bar, loading=checking and not batch.active)
        # Nothing to say while nothing runs, so the row only shows then.
        self.overall_row.setVisible(batch.active or checking)

        if not batch.active:
            if not checking:
                self.overall_bar.setValue(0)

            self.overall_label.setText("Refreshing catalog…" if checking else "")

            # Numbers, not a seen-it-running flag: a short batch can start and end between repaints.
            if batch.number != self.reported_batch:
                self.reported_batch = batch.number
                self.report_downloads(batch=batch)

            return

        self.overall_bar.setValue(int(1000 * batch.fraction))
        self.overall_label.setText(
            f"Processing {batch.finished}/{batch.count} mods · {100 * batch.fraction:.0f}%",
        )

    def report_downloads(self, batch: BatchProgress) -> None:
        if batch.saved or batch.failed:
            text = f"Downloaded {batch.saved}/{batch.count} mods."

            if batch.uploaded:
                text += f" Uploaded {batch.uploaded} to GitHub."

            if batch.deleted:
                copies = "local copy" if batch.deleted == 1 else "local copies"
                text += f" Deleted {batch.deleted} {copies}."

            if batch.upload_failed:
                text += f" {batch.upload_failed} failed on GitHub and stayed on disk."

            if batch.failed:
                text += f" {batch.failed} failed."

            if batch.cancelled:
                text += f" {batch.cancelled} cancelled."

            uploading = batch.uploaded or batch.upload_failed
            title = "Download and upload complete" if uploading else "Download complete"
            self.app.notify(title=title, text=text)
            self.app.later(show_message, title, text, self.app)

    # The button names the catalog in use; it is only set again when the name changes.
    def paint_catalogs(self, snapshot: Snapshot) -> None:
        active = next((catalog.name for catalog in snapshot.catalogs if catalog.folder == snapshot.active), "")
        text = active or "Add a catalog"

        if text != self.catalog_text:
            self.catalog_text = text
            chooser(widget=self.catalog_button, text=text, tip="Choose or manage the catalogs")

    # Switches to a catalog and reads it again; False when a download is running, which it must not disturb.
    def switch_catalog(self, folder: str, parent: QWidget | None = None) -> bool:
        if self.vault.busy():
            show_message(
                title="Downloading",
                message="Wait for downloads to finish before switching catalogs.",
                parent=parent or self.app,
            )

            return False

        self.vault.select_catalog(folder=folder)
        self.check()

        return True

    def paint_header(self, snapshot: Snapshot) -> None:
        idle = [item for item in self.items.values() if not item.job]
        self.updates = [item.id for item in idle if item.status == "update"]
        missing = [item for item in idle if item.status == "missing"]
        self.missing = [item.id for item in missing]
        self.redo_all = [item.id for item in idle if item.status == "ok"]
        have = sum(item.status != "missing" for item in self.items.values())
        parts = [f"{have}/{len(self.items)} downloaded"]

        if snapshot.checked_at:
            parts.append("checked at " + datetime.fromtimestamp(snapshot.checked_at).strftime("%H:%M:%S"))

        if snapshot.checking:
            self.summary.setText("")
            self.summary_spinner.start(text="Refreshing catalog…")
        else:
            self.summary_spinner.stop()
            self.summary.setText(" · ".join(parts) if self.vault.catalog else "No catalog")

        self.paint_note(
            note=self.new_label,
            text=plural(count=len(self.missing), word="new game") if self.missing else "",
        )
        self.paint_note(
            note=self.update_label,
            text=plural(count=len(self.updates), word="update") if self.updates else "",
        )

        if self.updates:
            size = sum(self.items[entry_id].size for entry_id in self.updates)
            self.update_all_button.setText(action_text(text="Update all", count=len(self.updates), size=size))

        self.update_all_button.setVisible(bool(self.updates))

        self.paint_chosen()
        self.stop_button.setVisible(self.vault.busy())
        self.refresh_action.setToolTip("Refreshing the catalog…" if snapshot.checking else "Refresh the catalog")
        self.refresh_action.setEnabled(not snapshot.checking)

        if not self.vault.catalog:
            self.app.set_footer(text="Click the catalog button to add your first catalog")
        elif snapshot.error:
            self.app.set_footer(text="Could not refresh catalog: " + snapshot.error, error=True)
        else:
            # The path sits under Destination already; the footer only speaks for hints and errors.
            self.app.set_footer(text="")
            self.open_button.setToolTip(f"Open {snapshot.dir}")

    @staticmethod
    def paint_note(note: QLabel, text: str) -> None:
        note.setText(text)
        note.setVisible(bool(text))
