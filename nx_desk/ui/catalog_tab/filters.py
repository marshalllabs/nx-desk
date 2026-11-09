from typing import Iterable

from ..rows import picked_text
from ..theme import STATUS_FILTERS
from .game_list import GameList


class Filters(GameList):
    def reset_filters(self) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.selected_genres.clear()
        self.genre_popup.set_choices(choices=[(genre, genre) for genre in self.genres], picked=set())
        self.paint_genre_button()
        self.picked.clear()
        self.selected = None
        self.shown_ids = None
        self.downloading.clear()
        self.detail_id = None
        self.detail_key = None
        self.set_filter(names=set())
        self.show_detail()

    def fill_genre_menu(self) -> None:
        self.genre_popup.set_choices(choices=[(genre, genre) for genre in self.genres], picked=self.selected_genres)
        self.paint_genre_button()

    def toggle_genre(self, genre: str, selected: bool) -> None:
        if selected:
            self.selected_genres.add(genre)

        else:
            self.selected_genres.discard(genre)

        self.paint_genre_button()
        self.rebuild_rows()

    def clear_genres(self) -> None:
        self.selected_genres.clear()
        self.fill_genre_menu()
        self.rebuild_rows()

    def paint_genre_button(self) -> None:
        self.genre_button.setText(picked_text(title="Genres", picked=sorted(self.selected_genres, key=str.lower)))

    def toggle_status(self, name: str, selected: bool) -> None:
        self.set_filter(names=self.status_filter | {name} if selected else self.status_filter - {name})

    # The notes on the Catalog card can be clicked from the log, so the list comes back too.
    def set_filter(self, names: Iterable[str]) -> None:
        self.status_filter = set(names)
        self.status_popup.set_choices(
            choices=[(name, row.label) for name, row in STATUS_FILTERS.items()],
            picked=self.status_filter,
        )
        texts = [row.label for name, row in STATUS_FILTERS.items() if name in self.status_filter]
        self.status_button.setText(picked_text(title="Status", picked=texts))
        self.view_switch.show_view(view="list")
        self.rebuild_rows()
        self.show_detail()
        self.current_view().scrollToTop()

    # A note shows only its own rows; clicking it again shows everything.
    def toggle_filter(self, name: str) -> None:
        self.set_filter(names=set() if self.status_filter == {name} else {name})
