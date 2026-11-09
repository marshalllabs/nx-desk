import math

from ...names import clean_game_name
from ...schemas.snapshot import ModRow
from ..rows import status_text, update_text
from ..style import set_role
from .art import ArtPane
from .detail_html import detail_html


class Detail(ArtPane):
    def show_detail(self) -> None:
        entry_id = self.selected
        item = self.items.get(entry_id) if entry_id else None
        key = (item.id, item.sha256) if item else None

        if key != self.detail_key:
            self.detail_key = key
            self.detail_id = entry_id
            self.art_id = None
            self.art_image = None
            self.art.hide()
            self.text.setHtml(detail_html(item=item) if item else "")
            self.fit_text()

        if not item:
            self.detail.setCurrentIndex(1)

            return

        self.detail.setCurrentIndex(0)
        self.show_art(item=item)
        self.name.setText(clean_game_name(name=item.name))
        self.paint_action(item=item)

    # The description is as tall as its text, at the width it has now, so it needs no scroll bar.
    def fit_text(self) -> None:
        document = self.text.document()
        document.setTextWidth(self.text.viewport().width())
        frame = 2 * self.text.frameWidth()
        self.text.setFixedHeight(math.ceil(document.size().height()) + frame)

    def fit_detail(self) -> None:
        self.fit_art()
        self.fit_text()

    def paint_action(self, item: ModRow) -> None:
        job = item.job
        active = job is not None and job.phase != "error"

        if job and job.phase == "error":
            message, text, role = "Error: " + job.message, "Retry", "accent"

        elif active:
            message, text, role = status_text(item=item), "Cancel", "danger"

        elif item.status == "update":
            message, text, role = update_text(item=item), "Update", "accent"

        elif item.status == "ok":
            where = "Online only" if item.remote else "Downloaded"
            message, text, role = f"{where}, up to date", "Re-download", None

        else:
            message, text, role = "Not downloaded", "Download", "accent"

        self.state_label.setText(message)
        self.action.setText(text)
        set_role(widget=self.action, role=role)

        if job is not None and active:
            self.progress.setValue(int(1000 * job.done / job.total) if job.total else 0)
            self.progress.show()

        else:
            self.progress.hide()
