import threading
from collections.abc import Callable

from PySide6.QtWidgets import (
    QFileDialog,
)

from ..dialogs import ask_text, ask_yes_no, confirm_typed, show_message
from ..widgets.basics import choice
from .state import UploadTabState


class ReleaseActions(UploadTabState):
    def auto_load(self) -> None:
        self.run(action=self.vault.prepare_uploads)

    @property
    def tag(self) -> str:
        return choice(box=self.release_box).strip()

    def save(self) -> None:
        self.vault.set_upload_settings(
            source=self.source.text(),
            repo=self.repo,
            tag=choice(box=self.release_box),
        )

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.app, "Choose the source folder", self.source.text() or "")

        if folder:
            self.source.setText(folder)

    def run(self, action: Callable[..., object], *args: object) -> None:
        if not self.vault.uploading():
            threading.Thread(target=action, args=args, daemon=True).start()

    def scan(self) -> None:
        self.run(action=self.vault.scan_upload)

    def load(self) -> None:
        self.run(action=self.vault.load_releases)

    def create_release(self) -> None:
        repo = self.repo

        if not repo or self.vault.uploading():
            return

        name = ask_text(
            title="Create release",
            message=f"Name of the new release in {repo}:",
            initial="",
            parent=self.app,
        )

        if not name:
            return

        if name in self.known_releases:
            show_message(title="Create release", message=f"Release {name} already exists.", parent=self.app)
        else:
            self.run(self.vault.create_upload_release, name)

    def edit_release(self) -> None:
        tag = self.tag

        if not tag or self.vault.uploading():
            return

        name = ask_text(title="Rename release", message=f"New name for release {tag}:", initial=tag, parent=self.app)

        if not name or name == tag:
            return

        text = f"Rename release {tag} to {name}?"
        catalog = self.vault.linked_catalog(tag=tag)

        if catalog:
            text += (
                f"\n\nRelease {tag} is linked to the catalog {catalog.name}. After renaming, the Catalog tab "
                "only counts games still on disk as downloaded or needing an update."
            )

        if ask_yes_no(title="Rename release", message=text, parent=self.app, action="Rename"):
            self.run(self.vault.rename_release, name)

    def delete_release(self) -> None:
        tag = self.tag

        if not tag or self.vault.uploading():
            return

        question = f"This permanently deletes release {tag} and every file on it. It cannot be undone."
        catalog = self.vault.linked_catalog(tag=tag)

        if catalog:
            question += (
                f"\n\nIt is linked to the catalog {catalog.name}, so games kept only on this release "
                "will show as not downloaded."
            )

        if confirm_typed(
            title="Delete release",
            message=question,
            word=tag,
            action="Delete release",
            parent=self.app,
        ):
            self.run(action=self.vault.delete_release)

    def refresh(self) -> None:
        self.run(action=self.vault.load_assets)
