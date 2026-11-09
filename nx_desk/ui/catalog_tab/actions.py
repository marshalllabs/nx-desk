import threading
from typing import Iterable, List

from ...utils.text import again, plural
from ..dialogs import ask_yes_no, confirm, show_message
from ..rows import mod_rows
from .state import CatalogTabState


class Actions(CatalogTabState):
    def has_mod_name(self) -> bool:
        if self.vault.mod_name:
            return True

        show_message(
            title="Mod name required",
            message="Enter the mod name under Saving before downloading.",
            parent=self.app,
        )
        self.mod_entry.setFocus()

        return False

    def act(self) -> None:
        item = self.items.get(self.detail_id or "")

        if not item:
            return

        job = item.job

        if job and job.phase != "error":
            if ask_yes_no(
                title="Stop download",
                message=f"Stop downloading {item.name}?",
                parent=self.app,
                action="Stop",
                danger=True,
                keep="Keep downloading",
            ):
                self.vault.cancel(entry_id=item.id)

        elif self.has_mod_name() and self.confirm_download(
            title=again(text="Download", done=item.status == "ok"),
            question=again(text="Download this mod?", done=item.status == "ok"),
            ids=[item.id],
        ):
            self.vault.clear_error(entry_id=item.id)
            self.vault.enqueue(ids=[item.id])

    def confirm_download(self, title: str, question: str, ids: Iterable[str]) -> bool:
        items = sorted(
            (self.items[entry_id] for entry_id in ids if entry_id in self.items),
            key=lambda item: item.name.lower(),
        )
        table = mod_rows(items=items)
        columns = table.columns
        rows = table.rows
        total = table.total

        return confirm(
            title=title,
            question=question.format(count=plural(count=len(rows), word="mod")),
            columns=columns,
            rows=rows,
            parent=self.app,
            total=total,
        )

    def update_all(self) -> None:
        ids = list(self.updates)

        if self.has_mod_name() and self.confirm_download(title="Update all", question="Update {count}?", ids=ids):
            self.vault.enqueue(ids=ids)

    def get_download(self) -> None:
        self.start_download(label=self.download_choice.label, ids=list(self.download_choice.ids))

    def get_redownload(self) -> None:
        self.start_download(label=self.redownload_choice.label, ids=list(self.redownload_choice.ids))

    # Enter on several picked rows: the new ones, or when none is new, the downloaded ones again.
    def get_chosen(self) -> None:
        if self.chosen:
            self.start_download(label="Download selected", ids=list(self.chosen))

        elif self.redo_chosen:
            self.start_download(label="Re-download selected", ids=list(self.redo_chosen))

    def start_download(self, label: str, ids: List[str]) -> None:
        verb = label.split(sep=" ")[0]

        if ids and self.has_mod_name() and self.confirm_download(title=label, question=verb + " {count}?", ids=ids):
            self.vault.enqueue(ids=ids)

    def stop_all(self) -> None:
        count = sum(job.phase != "error" for job in self.vault.snapshot_jobs())

        if count and ask_yes_no(
            title="Stop all",
            message=f"Stop {plural(count=count, word='download')}?",
            parent=self.app,
            action="Stop all",
            danger=True,
            keep="Keep downloading",
        ):
            self.vault.cancel_all()

    def check(self) -> None:
        self.app.catalog.reset_filters()
        threading.Thread(target=self.vault.check, daemon=True).start()
