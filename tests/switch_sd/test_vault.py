from unittest import mock

from nx_desk import vault
from nx_desk.catalog.title_ids import parse_title_ids
from tests.helpers import mod
from tests.switch_sd.case import TITLE, SDCase


class SwitchVaultTests(SDCase):
    def setUp(self) -> None:
        super().setUp()
        self.store = vault.Vault(base=self.base / "data")

    def test_first_detected_card_is_selected_and_scanned_automatically(self) -> None:
        self.put(relative=f"{TITLE}/romfs/a")
        self.store.refresh_switch_cards(volumes=[self.volume])
        job = self.store.switch_snapshot()
        self.assertEqual(first=len(job.cards), second=1)
        self.assertEqual(first=job.selected, second=str(self.root))
        self.assertEqual(first=len(job.titles), second=1)
        self.put(relative=f"{TITLE}/romfs/a")
        self.store.select_switch_card(root=str(self.root))
        self.store.refresh_switch_cards(volumes=[self.volume], force=True)
        self.assertEqual(first=len(self.store.switch_snapshot().titles), second=1)

    def test_replacement_rescans_and_removal_clears_selection(self) -> None:
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.store.select_switch_card(root=str(self.root))
        self.store.refresh_switch_cards(volumes=[self.volume], force=True)
        (self.root / "atmosphere" / "package3").write_bytes(data=b"replacement")
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.assertEqual(first=self.store.switch_snapshot().selected, second=str(self.root))
        self.store.refresh_switch_cards(volumes=[])
        self.assertEqual(first=self.store.switch_snapshot().cards, second=[])
        self.assertEqual(first=self.store.switch_snapshot().selected, second="")

    def test_selection_is_retained_then_falls_back_to_remaining_card(self) -> None:
        other_root = self.base / "other-card"
        (other_root / "atmosphere").mkdir(parents=True)
        (other_root / "atmosphere" / "package3").write_bytes(data=b"synthetic")
        other = self.volume.model_copy(update={"root": other_root})
        self.put(relative=f"{TITLE}/romfs/a")
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.store.refresh_switch_cards(volumes=[other, self.volume])
        self.assertEqual(first=self.store.switch_snapshot().selected, second=str(self.root))
        self.store.refresh_switch_cards(volumes=[other])
        job = self.store.switch_snapshot()
        self.assertEqual(first=job.selected, second=str(other_root))
        self.assertEqual(first=job.titles, second=[])

    def test_polling_does_not_rehash_an_unchanged_card(self) -> None:
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.store.select_switch_card(root=str(self.root))
        self.store.refresh_switch_cards(volumes=[self.volume], force=True)

        with mock.patch(target="nx_desk.vault.switch_sd.scan.scan") as scan:
            self.store.refresh_switch_cards(volumes=[self.volume])

        scan.assert_not_called()

    def test_system_and_sysmodule_names_use_the_complete_title_feed(self) -> None:
        system = "0100000000001000"
        module = "00FF00000000A001"
        self.put(relative=f"{system}/romfs/a")
        self.put(relative=f"{module}/exefs.nsp")
        self.store.title_rows = parse_title_ids(
            data={
                "games": {TITLE: "Catalog game"},
                "system": {system: {"name": "Synthetic system applet", "group": "System Applets"}},
                "sysmodules": {module: "Synthetic service"},
            },
        )
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.store.select_switch_card(root=str(self.root))
        self.store.refresh_switch_cards(volumes=[self.volume], force=True)
        rows = {row.title_id: row for row in self.store.switch_snapshot().titles}
        self.assertEqual(
            first=(rows[system].name, rows[system].category),
            second=("Synthetic system applet", "System content"),
        )
        self.assertEqual(first=(rows[module].name, rows[module].category), second=("Synthetic service", "Sysmodule"))
        self.assertEqual(first=rows[module].kinds, second=["exefs.nsp"])

    def test_title_feed_refresh_relabels_content_without_reading_the_card_again(self) -> None:
        self.put(relative=f"{TITLE}/romfs/a")
        self.store.refresh_switch_cards(volumes=[self.volume])
        self.store.select_switch_card(root=str(self.root))
        self.store.refresh_switch_cards(volumes=[self.volume], force=True)
        self.assertEqual(first=self.store.switch_snapshot().titles[0].name, second="")
        self.store._keep_title_rows(rows=parse_title_ids(data={"sysmodules": {TITLE: "New synthetic service"}}))

        with mock.patch(target="nx_desk.vault.switch_sd.scan.scan") as scan:
            self.store.refresh_switch_cards(volumes=[self.volume])

        scan.assert_not_called()
        row = self.store.switch_snapshot().titles[0]
        self.assertEqual(first=(row.name, row.category), second=("New synthetic service", "Sysmodule"))

    def test_feed_names_take_priority_over_catalog_and_catalog_is_a_fallback(self) -> None:
        self.store.title_rows = parse_title_ids(data={"games": {TITLE: "Feed name"}})
        self.store.items = [mod(title_id=TITLE, name="Catalog alias")]
        self.assertEqual(first=self.store._switch_names()[TITLE].name, second="Feed name")
        self.store.title_rows = []
        self.assertEqual(first=self.store._switch_names()[TITLE].name, second="Catalog alias")
