from unittest import mock

from nx_desk import net
from nx_desk.schemas.catalog import Mod
from tests.artwork.case import GRID, HERO, ArtCase, FakeSteamGridDB
from tests.helpers import mod


class ArtSourceTests(ArtCase):
    def item(self, name: str = "Game") -> Mod:
        return mod(name=name, cover="https://catalog.test/c.png", background="https://catalog.test/b.png")

    def test_without_a_key_the_catalog_art_is_used_and_nothing_is_asked(self) -> None:
        fake = FakeSteamGridDB()

        with mock.patch.object(net, "http_get", side_effect=fake):
            sources = self.vault.art_sources(item=self.item())

        self.assertEqual(sources, ("https://catalog.test/c.png", "https://catalog.test/b.png"))
        self.assertEqual(fake.calls, [])

    def test_with_a_key_steamgriddb_art_comes_first(self) -> None:
        self.vault.set_art_key(key="abc123")
        fake = FakeSteamGridDB()

        with mock.patch.object(net, "http_get", side_effect=fake):
            sources = self.vault.art_sources(item=self.item())

        self.assertEqual(sources, (GRID, HERO))
        self.assertEqual(set(fake.keys), {"Bearer abc123"})

    def test_a_game_it_lacks_keeps_the_catalog_art_and_is_not_asked_again(self) -> None:
        self.vault.set_art_key(key="abc123")
        fake = FakeSteamGridDB(games={})

        with mock.patch.object(net, "http_get", side_effect=fake):
            first = self.vault.art_sources(item=self.item())
            self.vault.art_sources(item=self.item())

        self.assertEqual(first, ("https://catalog.test/c.png", "https://catalog.test/b.png"))
        self.assertEqual(len(fake.calls), 1)

    def test_a_refused_key_stops_lookups_until_a_new_key(self) -> None:
        self.vault.set_art_key(key="bad")
        fake = FakeSteamGridDB(refuse=401)

        with mock.patch.object(net, "http_get", side_effect=fake):
            self.vault.art_sources(item=self.item())
            self.vault.art_sources(item=self.item(name="Other"))

        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(self.vault.art_status()[1])
        self.vault.set_art_key(key="good")
        self.assertEqual(self.vault.art_status()[1], "")

    def test_a_rate_limit_pauses_lookups(self) -> None:
        self.vault.set_art_key(key="abc123")
        fake = FakeSteamGridDB(refuse=429)

        with mock.patch.object(net, "http_get", side_effect=fake):
            self.vault.art_sources(item=self.item())
            sources = self.vault.art_sources(item=self.item(name="Other"))

        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(sources, ("https://catalog.test/c.png", "https://catalog.test/b.png"))

    def test_a_new_url_replaces_the_saved_file(self) -> None:
        art_dir = self.folder / "covers" / "x"
        art_dir.mkdir(parents=True)
        item = self.item()
        fake = FakeSteamGridDB()

        with mock.patch.object(net, "http_get", side_effect=fake):
            old = self.vault.fetch_art(item=item, kind="cover", url="https://catalog.test/c.png", art_dir=art_dir)
            self.vault.fetch_art(item=item, kind="cover", url="https://catalog.test/c.png", art_dir=art_dir)
            new = self.vault.fetch_art(item=item, kind="cover", url="https://cdn.test/grid/cover.jpg", art_dir=art_dir)

        # The same URL is not fetched twice; a new one is another file name, and the older file goes.
        self.assertEqual(len(fake.images), 2)
        assert old is not None and new is not None
        self.assertFalse(old.exists())
        self.assertEqual(sorted(path.name for path in art_dir.iterdir()), ["game-cover.82fd59b6.jpg"])
        self.assertEqual(old.name, "game-cover.dd61c0c0.png")
