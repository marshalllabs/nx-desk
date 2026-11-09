from typing import Tuple, Union

from PySide6.QtCore import (
    QItemSelectionModel,
    Qt,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
)

from ...names import clean_game_name
from ...schemas.snapshot import ModRow
from ..rows import action_text, download_scopes
from ..theme import LIST_COLUMNS, LIST_SORTABLE, status_matches
from .detail import Detail


class GameList(Detail):
    # The list or the grid, whichever is shown; both read the same model.
    def current_view(self) -> QAbstractItemView:
        return self.grid if self.mode == "grid" else self.table

    # The grid has no column headers, so its Sort menu picks the column here.
    def sort_by_name(self, name: str) -> None:
        self.list_sort.toggle(column=name)
        self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(LIST_COLUMNS) - 1)
        self.rebuild_rows()

    def sort_list(self, column: int) -> None:
        name = LIST_COLUMNS[column].key

        if name in LIST_SORTABLE:
            self.list_sort.toggle(column=name)
            self.model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(LIST_COLUMNS) - 1)
            self.rebuild_rows()

    def list_order(self, item: ModRow) -> Tuple[Union[int, str], Union[int, str]]:
        name = clean_game_name(name=item.name).casefold()

        return (item.size, name) if self.list_sort.column == "size" else (name, 0)

    def rebuild_rows(self) -> None:
        shown = [item for item in self.items.values() if self.matches(item=item)]
        shown.sort(key=self.list_order, reverse=not self.list_sort.ascending)
        ids = [item.id for item in shown]
        changed = ids != self.shown_ids
        self.shown_ids = ids

        if self.model.set_rows(ids=ids, items=self.items) or changed:
            if self.selected not in ids:
                self.selected = ids[0] if ids else None

            self.picked = (self.picked & set(ids)) or ({self.selected} if self.selected else set())
            self.restore_selection()

        self.paint_list_empty(empty=not ids)

    # A reset model forgets its selection, so the picked rows are chosen again.
    def restore_selection(self) -> None:
        selection = self.current_view().selectionModel()
        self.restoring = True

        try:
            selection.clearSelection()
            flags = QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows

            ids = self.shown_ids or []

            for entry_id in self.picked:
                selection.select(self.model.index(ids.index(entry_id), 0), flags)

            if self.selected is not None:
                index = self.model.index(ids.index(self.selected), 0)
                selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)

        finally:
            self.restoring = False

        self.paint_chosen()

    def selection_changed(self, *_: object) -> None:
        if self.restoring:
            return

        ids = self.shown_ids or []
        rows = {index.row() for index in self.current_view().selectionModel().selectedIndexes()}
        self.picked = {ids[row] for row in rows if row < len(ids)}
        current = self.current_view().currentIndex()

        if current.isValid() and current.row() < len(ids):
            self.selected = ids[current.row()]

        self.show_detail()
        self.paint_chosen()

    def select(self, entry_id: str) -> None:
        if entry_id not in (self.shown_ids or []):
            return

        index = self.model.index(self.shown_ids.index(entry_id), 0)  # type: ignore[union-attr]
        flags = QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
        view = self.current_view()
        view.selectionModel().setCurrentIndex(index, flags)
        view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def paint_list_empty(self, empty: bool) -> None:
        filtered = self.search.text().strip() or self.selected_genres or self.status_filter
        message = "No mods match these filters" if filtered else "No mods in this catalog"

        for note, view in ((self.list_empty, self.table), (self.grid_empty, self.grid)):
            note.setText(message)
            note.setGeometry(view.viewport().rect())
            note.setVisible(empty)

    def paint_chosen(self) -> None:
        found = (self.items.get(entry_id) for entry_id in self.shown_ids or [] if entry_id in self.picked)
        idle = [item for item in found if item and not item.job]
        self.chosen = [item.id for item in idle if item.status in ("missing", "update")]
        self.redo_chosen = [item.id for item in idle if item.status == "ok"]
        choices = download_scopes(
            picked=len(self.picked),
            new=self.missing,
            done=self.redo_all,
            picked_new=self.chosen,
            picked_done=self.redo_chosen,
        )
        self.download_choice = choices.download
        self.redownload_choice = choices.redownload
        several = len(self.picked) > 1
        self.download_action.setToolTip("Download the selected new mods" if several else "Download every new mod")
        self.redownload_action.setToolTip(
            "Download the selected mods again" if several else "Download every downloaded mod again",
        )

        # Count and size on each button, the same as the GitHub tab's buttons.
        for action, choice in (
            (self.download_action, self.download_choice),
            (self.redownload_action, self.redownload_choice),
        ):
            ids = choice.ids
            label = choice.label
            size = sum(self.items[entry_id].size for entry_id in ids if entry_id in self.items)
            action.setText(action_text(text=label, count=len(ids), size=size))
            action.setEnabled(bool(ids))

    # A mod that starts downloading becomes the selected row, scrolled into view. Two can start
    # together, so the one higher in the list wins.
    def follow_downloads(self) -> None:
        now = {entry_id for entry_id, item in self.items.items() if (job := item.job) and job.phase == "downloading"}
        started = now - self.downloading
        self.downloading = now
        shown = [entry_id for entry_id in self.shown_ids or [] if entry_id in started]

        if shown:
            self.select(entry_id=shown[0])

    def matches(self, item: ModRow) -> bool:
        query = self.search.text().strip().lower()
        haystack = " ".join(
            [item.name, clean_game_name(name=item.name), item.developer, item.translator, *item.tags],
        ).lower()

        return (
            (not query or query in haystack)
            and (not self.selected_genres or not self.selected_genres.isdisjoint(item.tags))
            and status_matches(item=item, picked=self.status_filter)
        )
