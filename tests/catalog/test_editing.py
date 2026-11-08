import json
from unittest import mock

from nx_desk import names, net, vault
from tests.catalog.case import CatalogCase, active
from tests.helpers import entry, job


class EditTests(CatalogCase):
    def test_editing_keeps_the_folder_and_its_downloads(self) -> None:
        self.store.set_mod_name(name="VI")
        first = self.add(name="A", url="https://a.test/c.json")
        item = self.store.items[0]
        target = self.store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=target)
        result = self.edit(folder="a", url="https://new.test/c.json", games=("one", "two"), name="Renamed")
        self.assertIs(result.catalog, first)
        # Without gh the folder, and with it the release, keep their names.
        self.assertEqual((result.catalog.folder, result.catalog.name, result.count), ("a", "Renamed", 2))
        self.assertTrue(result.notes and "gh is not available" in result.notes[0])
        self.assertEqual(len(self.store.items), 2)
        self.assertEqual(self.store.status_of(entry=self.store.items[0]), "ok")
        reopened = vault.Vault(base=self.dir)
        self.assertEqual(reopened.catalogs[0].url, "https://new.test/c.json")
        self.assertEqual(len(reopened.items), 2)

    def test_editing_an_inactive_catalog_leaves_the_shown_list(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json", games=("two", "three"))
        self.edit(folder="a", url="https://a.test/other.json", games=("four",))
        self.assertEqual([item.id for item in self.store.items], ["two", "three"])
        self.store.select_catalog(folder="a")
        self.assertEqual([item.id for item in self.store.items], ["four"])

    def test_an_empty_name_keeps_the_old_one(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.assertEqual(self.edit(folder="a", url="https://a.test/c.json").catalog.name, "A")

    def test_a_bad_edit_changes_nothing(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json")

        with self.assertRaises(ValueError):
            self.edit(folder="a", url="http://a.test/c.json")

        with self.assertRaises(ValueError):
            self.edit(folder="a", url="https://b.test/c.json")

        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"not json"

        with mock.patch.object(net, "http_get", return_value=response), self.assertRaises(ValueError):
            self.store.edit_catalog(folder="a", name="X", url="https://x.test/c.json")

        self.assertEqual(self.store.catalogs[0].url, "https://a.test/c.json")
        self.assertEqual(self.store.catalogs[0].name, "A")

    def test_cannot_edit_the_active_catalog_while_downloading(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.store.jobs["x"] = job(phase="downloading")

        with self.assertRaises(ValueError):
            self.edit(folder="a", url="https://new.test/c.json")

        self.assertEqual(active(store=self.store).url, "https://a.test/c.json")

    def test_a_check_from_before_an_edit_is_ignored(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        response = mock.MagicMock()

        def edit_then_read(*_: object) -> bytes:
            active(store=self.store).url = "https://new.test/c.json"

            return json.dumps(obj={"mods": [entry(id="late")]}).encode()

        response.__enter__.return_value.read.side_effect = edit_then_read

        with mock.patch.object(net, "http_get", return_value=response):
            self.store.check()

        self.assertEqual([item.id for item in self.store.items], ["one"])

    def test_check_failure_keeps_the_old_list(self) -> None:
        self.add(name="A", url="https://a.test/c.json")

        with mock.patch.object(net, "http_get", side_effect=OSError("offline")):
            self.store.check()

        self.assertEqual(len(self.store.items), 1)
        self.assertEqual(self.store.check_error, "offline")

    def test_a_late_result_does_not_touch_the_new_catalog(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json", games=("two", "three"))
        response = mock.MagicMock()

        def switch_then_read(*_: object) -> bytes:
            self.store.select_catalog(folder="a")

            return json.dumps(obj={"mods": [entry(id="late")]}).encode()

        response.__enter__.return_value.read.side_effect = switch_then_read

        with mock.patch.object(net, "http_get", return_value=response):
            self.store.check()

        self.assertEqual([item.id for item in self.store.items], ["one"])
