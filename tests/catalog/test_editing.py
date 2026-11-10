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
        self.assertIs(expr1=result.catalog, expr2=first)
        # Without GitHub authentication the folder, and with it the release, keep their names.
        self.assertEqual(first=(result.catalog.folder, result.catalog.name, result.count), second=("a", "Renamed", 2))
        self.assertTrue(expr=result.notes and "GitHub authentication is unavailable" in result.notes[0])
        self.assertEqual(first=len(self.store.items), second=2)
        self.assertEqual(first=self.store.status_of(entry=self.store.items[0]), second="ok")
        reopened = vault.Vault(base=self.dir)
        self.assertEqual(first=reopened.catalogs[0].url, second="https://new.test/c.json")
        self.assertEqual(first=len(reopened.items), second=2)

    def test_editing_an_inactive_catalog_leaves_the_shown_list(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json", games=("two", "three"))
        self.edit(folder="a", url="https://a.test/other.json", games=("four",))
        self.assertEqual(first=[item.id for item in self.store.items], second=["two", "three"])
        self.store.select_catalog(folder="a")
        self.assertEqual(first=[item.id for item in self.store.items], second=["four"])

    def test_an_empty_name_keeps_the_old_one(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.assertEqual(first=self.edit(folder="a", url="https://a.test/c.json").catalog.name, second="A")

    def test_a_bad_edit_changes_nothing(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json")

        with self.assertRaises(expected_exception=ValueError):
            self.edit(folder="a", url="http://a.test/c.json")

        with self.assertRaises(expected_exception=ValueError):
            self.edit(folder="a", url="https://b.test/c.json")

        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"not json"

        with (
            mock.patch.object(target=net, attribute="http_get", return_value=response),
            self.assertRaises(expected_exception=ValueError),
        ):
            self.store.edit_catalog(folder="a", name="X", url="https://x.test/c.json")

        self.assertEqual(first=self.store.catalogs[0].url, second="https://a.test/c.json")
        self.assertEqual(first=self.store.catalogs[0].name, second="A")

    def test_cannot_edit_the_active_catalog_while_downloading(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.store.jobs["x"] = job(phase="downloading")

        with self.assertRaises(expected_exception=ValueError):
            self.edit(folder="a", url="https://new.test/c.json")

        self.assertEqual(first=active(store=self.store).url, second="https://a.test/c.json")

    def test_a_check_from_before_an_edit_is_ignored(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        response = mock.MagicMock()

        def edit_then_read(*_: object) -> bytes:
            active(store=self.store).url = "https://new.test/c.json"

            return json.dumps(obj={"mods": [entry(id="late")]}).encode()

        response.__enter__.return_value.read.side_effect = edit_then_read

        with mock.patch.object(target=net, attribute="http_get", return_value=response):
            self.store.check()

        self.assertEqual(first=[item.id for item in self.store.items], second=["one"])

    def test_check_failure_keeps_the_old_list(self) -> None:
        self.add(name="A", url="https://a.test/c.json")

        with mock.patch.object(target=net, attribute="http_get", side_effect=OSError("offline")):
            self.store.check()

        self.assertEqual(first=len(self.store.items), second=1)
        self.assertEqual(first=self.store.check_error, second="offline")

    def test_a_late_result_does_not_touch_the_new_catalog(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json", games=("two", "three"))
        response = mock.MagicMock()

        def switch_then_read(*_: object) -> bytes:
            self.store.select_catalog(folder="a")

            return json.dumps(obj={"mods": [entry(id="late")]}).encode()

        response.__enter__.return_value.read.side_effect = switch_then_read

        with mock.patch.object(target=net, attribute="http_get", return_value=response):
            self.store.check()

        self.assertEqual(first=[item.id for item in self.store.items], second=["one"])
