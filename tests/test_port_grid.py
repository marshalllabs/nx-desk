import json
import tempfile
import unittest
from pathlib import Path

from nx_desk import vault
from nx_desk.ui.cards.layout import MAX_CELL, MIN_CELL, cell_size, columns, cover_size, visible_slice


class GridLayoutTests(unittest.TestCase):
    def test_a_narrow_view_has_one_column_of_the_smallest_cell(self) -> None:
        self.assertEqual((columns(width=100), columns(width=0)), (1, 1))
        self.assertEqual(cell_size(width=100, line=20)[0], MIN_CELL)

    def test_cells_share_the_width_so_no_strip_is_left_at_the_right(self) -> None:
        for width in (1100, 1300, 1400, 1650):
            cell, _ = cell_size(width=width, line=20)
            per_row = columns(width=width)
            # What is left is only the remainder of the division, less than a pixel for each card.
            self.assertLess(width - per_row * cell, per_row)

    def test_a_cell_is_never_wider_than_the_most(self) -> None:
        # One column in 367 px would be 367 px wide, so it stops at the most.
        self.assertEqual(cell_size(width=367, line=20)[0], MAX_CELL)
        self.assertEqual(cell_size(width=1100, line=20)[0], 220)
        self.assertEqual(cell_size(width=1400, line=20)[0], 200)

    def test_the_cover_keeps_its_tall_shape(self) -> None:
        self.assertEqual(cover_size(cell_width=200), (176, 264))
        self.assertEqual(cover_size(cell_width=MIN_CELL), (160, 240))

    def test_a_cell_is_as_tall_as_its_cover_and_three_lines_of_text(self) -> None:
        # 4 + 4 margins, 8 + 8 padding, 6 gap, 264 cover and 3 lines of 20.
        self.assertEqual(cell_size(width=1400, line=20)[1], 8 + 8 + 264 + 6 + 60 + 8)
        self.assertEqual(cell_size(width=1400, line=30)[1] - cell_size(width=1400, line=20)[1], 30)

    def test_the_top_of_the_list_shows_the_first_rows_and_one_more_row_of_cards(self) -> None:
        cell = cell_size(width=1000, line=20)
        start, end = visible_slice(scroll=0, width=1000, height=650, cell=cell, total=434)
        per_row = columns(width=1000)
        rows_in_view = -(-650 // cell[1])
        self.assertEqual((start, end), (0, (rows_in_view + 1) * per_row))

    def test_scrolling_moves_the_window_down(self) -> None:
        cell = cell_size(width=1000, line=20)
        per_row = columns(width=1000)
        start, _ = visible_slice(scroll=cell[1] * 10, width=1000, height=650, cell=cell, total=434)
        self.assertEqual(start, 10 * per_row)

    def test_the_window_stops_at_the_last_entry(self) -> None:
        cell = cell_size(width=1000, line=20)
        self.assertEqual(visible_slice(scroll=cell[1] * 500, width=1000, height=650, cell=cell, total=434), (434, 434))
        self.assertEqual(visible_slice(scroll=0, width=1000, height=650, cell=cell, total=0), (0, 0))
        self.assertEqual(visible_slice(scroll=0, width=1000, height=650, cell=cell, total=3), (0, 3))


class PortsViewSettingTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_the_list_is_the_default(self) -> None:
        self.assertEqual(vault.Vault(base=self.folder).ports_view, "list")

    def test_the_grid_is_remembered(self) -> None:
        store = vault.Vault(base=self.folder)
        store.set_ports_view(view="grid")
        self.assertEqual(vault.Vault(base=self.folder).ports_view, "grid")
        store.set_ports_view(view="list")
        self.assertEqual(vault.Vault(base=self.folder).ports_view, "list")

    def test_an_odd_value_means_the_list(self) -> None:
        store = vault.Vault(base=self.folder)
        store.set_ports_view(view="cards")
        self.assertEqual(store.ports_view, "list")
        index = self.folder / "settings.json"
        index.write_text(json.dumps(obj={"ports_view": "cards"}), encoding="utf-8")
        self.assertEqual(vault.Vault(base=self.folder).ports_view, "list")


class CatalogViewSettingTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_the_list_is_the_default_and_the_grid_is_remembered_apart_from_the_ports_view(self) -> None:
        store = vault.Vault(base=self.folder)
        self.assertEqual(store.catalog_view, "list")
        store.set_catalog_view(view="grid")
        again = vault.Vault(base=self.folder)
        self.assertEqual((again.catalog_view, again.ports_view), ("grid", "list"))

    def test_an_odd_value_means_the_list(self) -> None:
        store = vault.Vault(base=self.folder)
        store.set_catalog_view(view="cards")
        self.assertEqual(store.catalog_view, "list")
