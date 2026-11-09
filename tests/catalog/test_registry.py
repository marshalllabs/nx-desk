from unittest import mock

from nx_desk import names, net, vault
from tests.catalog.case import CatalogCase, active
from tests.helpers import job


class RegistryTests(CatalogCase):
    def test_starts_empty(self) -> None:
        self.assertIsNone(obj=self.store.catalog)
        self.assertEqual(first=self.store.items, second=[])
        self.store.check()
        self.assertIsNone(obj=self.store.check_error)

    def test_adding_switches_to_the_new_catalog(self) -> None:
        self.add(name="First One", url="https://a.test/c.json")
        self.assertEqual(first=active(store=self.store).folder, second="first-one")
        self.assertEqual(first=[item.id for item in self.store.items], second=["one"])

    def test_rejects_bad_urls_and_duplicates(self) -> None:
        with self.assertRaises(expected_exception=ValueError):
            self.store.add_catalog(name="x", url="http://a.test/c.json")

        self.add(name="x", url="https://a.test/c.json")

        with self.assertRaises(expected_exception=ValueError):
            self.store.add_catalog(name="y", url="https://a.test/c.json")

    def test_rejects_files_that_are_not_catalogs(self) -> None:
        for body in (b"not json", b"[]", b'{"mods": []}'):
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = body

            with (
                mock.patch.object(target=net, attribute="http_get", return_value=response),
                self.assertRaises(expected_exception=ValueError),
            ):
                self.store.add_catalog(name="x", url="https://a.test/c.json")

        self.assertEqual(first=self.store.catalogs, second=[])

    def test_same_name_gets_its_own_folder(self) -> None:
        self.add(name="Same", url="https://a.test/1.json")
        self.assertEqual(first=self.add(name="Same", url="https://a.test/2.json").folder, second="same-2")

    def test_catalogs_keep_separate_games_and_state(self) -> None:
        self.store.set_mod_name(name="VI")
        first = self.add(name="A", url="https://a.test/c.json", games=("one",))
        item = self.store.items[0]
        target = self.store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=target)
        self.add(name="B", url="https://b.test/c.json", games=("one", "two"))
        self.assertEqual(first=len(self.store.items), second=2)
        self.assertEqual(first=self.store.status_of(entry=self.store.items[0]), second="missing")
        self.store.select_catalog(folder=first.folder)
        self.assertEqual(first=len(self.store.items), second=1)
        self.assertEqual(first=self.store.status_of(entry=self.store.items[0]), second="ok")

    def test_selection_survives_a_restart(self) -> None:
        first = self.add(name="A", url="https://a.test/c.json")
        self.add(name="B", url="https://b.test/c.json")
        self.store.select_catalog(folder=first.folder)
        reopened = vault.Vault(base=self.dir)
        self.assertEqual(first=active(store=reopened).folder, second="a")
        self.assertEqual(first=len(reopened.catalogs), second=2)
        self.assertEqual(first=len(reopened.items), second=1)

    def test_removing_keeps_downloads_and_moves_on(self) -> None:
        self.add(name="A", url="https://a.test/c.json")
        second = self.add(name="B", url="https://b.test/c.json")
        kept = self.store.root / "kept.zip"
        kept.parent.mkdir(parents=True)
        kept.write_bytes(data=b"zip")
        self.store.remove_catalog(folder=second.folder)
        self.assertEqual(first=active(store=self.store).folder, second="a")
        self.assertTrue(expr=kept.exists())
        self.store.remove_catalog(folder="a")
        self.assertIsNone(obj=self.store.catalog)

    def test_cannot_add_while_downloading(self) -> None:
        self.store.jobs["x"] = job(phase="downloading")

        with self.assertRaises(expected_exception=ValueError):
            self.add(name="x", url="https://a.test/c.json")
