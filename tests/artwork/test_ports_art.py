import time
from typing import Dict, List, Optional
from unittest import mock

from nx_desk import net
from nx_desk.config import ART_LOOKUP_RULES
from nx_desk.schemas.artwork import ArtLookup, ArtSources
from nx_desk.schemas.port import Port
from tests.artwork.case import GRID, HERO, ArtCase, FakeSteamGridDB


class PortArtTests(ArtCase):
    def port(self, name: str = "Game") -> Port:
        return Port(id=f"owner/{name.lower()}", name=name, platform="PC")

    def test_without_a_key_nothing_is_asked(self) -> None:
        fake = FakeSteamGridDB()

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            self.assertIsNone(obj=self.vault.steamgrid_art(item=self.port()))

        self.assertEqual(first=fake.calls, second=[])

    def test_with_a_key_steamgriddb_gives_the_art(self) -> None:
        self.vault.set_art_key(key="abc123")
        fake = FakeSteamGridDB()

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            self.assertEqual(
                first=self.vault.steamgrid_art(item=self.port()),
                second=ArtSources(cover=GRID, background=HERO),
            )

    def test_a_game_it_lacks_has_no_urls_and_is_not_asked_again(self) -> None:
        self.vault.set_art_key(key="abc123")
        fake = FakeSteamGridDB(games={})

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            self.assertEqual(first=self.vault.steamgrid_art(item=self.port()), second=ArtSources())
            self.assertEqual(first=self.vault.steamgrid_art(item=self.port()), second=ArtSources())

        self.assertEqual(first=len(fake.calls), second=1)

    def test_a_refused_key_gives_no_answer(self) -> None:
        self.vault.set_art_key(key="abc123")

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB(refuse=401)):
            self.assertIsNone(obj=self.vault.steamgrid_art(item=self.port()))

    def test_ports_save_their_art_in_their_own_folder_and_leave_the_catalogs_alone(self) -> None:
        port = self.port()
        art_dir = self.vault.ports_art_dir
        art_dir.mkdir(parents=True)

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB()):
            path = self.vault.fetch_art(item=port, kind="cover", url=GRID, art_dir=art_dir)

        assert path is not None
        self.assertEqual(first=path.parent, second=self.folder / "covers" / "_ports")
        # Which URL a file came from is in its name, so there is no list of them.
        self.assertEqual(first=list(self.folder.rglob(pattern="*.covers.json")), second=[])

    def test_art_of_entries_that_left_the_list_is_removed(self) -> None:
        keep, gone = self.port(), self.port(name="Gone")
        art_dir = self.vault.ports_art_dir
        art_dir.mkdir(parents=True)

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB()):
            for port in (keep, gone):
                self.vault.fetch_art(item=port, kind="cover", url=GRID, art_dir=art_dir)

        self.vault.prune_art(items=[keep], art_dir=art_dir)
        self.assertEqual(first=[path.name for path in art_dir.iterdir()], second=["game-cover.751ef911.png"])


class ArtBusyTests(ArtCase):
    CDN = "https://cdn2.steamgriddb.com/grid/cover.png"

    def watched(self, fake: FakeSteamGridDB, seen: List[bool]) -> object:
        def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> object:
            seen.append(self.vault.art_busy())

            return fake(url=url, headers=headers, timeout=timeout)

        return get

    def test_a_lookup_counts_while_it_runs_and_not_after(self) -> None:
        self.vault.set_art_key(key="abc123")
        seen: List[bool] = []
        self.assertFalse(expr=self.vault.art_busy())

        with mock.patch.object(
            target=net,
            attribute="http_get",
            side_effect=self.watched(fake=FakeSteamGridDB(), seen=seen),
        ):
            self.vault.steamgrid_art(item=Port(id="o/game", name="Game", platform="PC"))

        self.assertTrue(expr=seen and all(seen))
        self.assertFalse(expr=self.vault.art_busy())

    def test_only_steamgriddb_images_count(self) -> None:
        port = Port(id="o/game", name="Game", platform="PC")
        art_dir = self.vault.ports_art_dir
        art_dir.mkdir(parents=True)
        seen: List[bool] = []

        with mock.patch.object(
            target=net,
            attribute="http_get",
            side_effect=self.watched(fake=FakeSteamGridDB(), seen=seen),
        ):
            self.vault.fetch_art(item=port, kind="cover", url=self.CDN, art_dir=art_dir)
            self.vault.fetch_art(item=port, kind="background", url="https://catalog.test/b.png", art_dir=art_dir)

        self.assertEqual(first=seen, second=[True, False])
        self.assertFalse(expr=self.vault.art_busy())

    def test_a_failed_request_does_not_leave_it_busy(self) -> None:
        self.vault.set_art_key(key="abc123")

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB(refuse=500)):
            self.vault.steamgrid_art(item=Port(id="o/game", name="Game", platform="PC"))

        self.assertFalse(expr=self.vault.art_busy())


class LookupRulesTests(ArtCase):
    # A new key forgets the lookups that found nothing, so the key comes first.
    def saved(self, rules: int, game_id: int = 0, cover: str = "") -> None:
        self.vault.set_art_key(key="abc123")
        found = ArtLookup(game_id=game_id, cover=cover, checked_at=time.time(), rules=rules)
        self.vault.art_lookups["Game"] = found

    def asked(self) -> int:
        fake = FakeSteamGridDB()

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            self.vault.steamgrid_art(item=Port(id="o/game", name="Game", platform="PC"))

        return len(fake.calls)

    def test_an_old_lookup_that_found_nothing_is_asked_again(self) -> None:
        self.saved(rules=0)
        self.assertGreater(a=self.asked(), b=0)

    def test_an_old_lookup_that_found_a_cover_is_kept(self) -> None:
        self.saved(rules=0, game_id=7, cover=GRID)
        self.assertEqual(first=self.asked(), second=0)

    def test_a_lookup_under_the_current_rules_is_kept_even_with_nothing(self) -> None:
        self.saved(rules=ART_LOOKUP_RULES)
        self.assertEqual(first=self.asked(), second=0)


class NoCatalogTests(ArtCase):
    def test_with_no_catalog_nothing_is_made_for_its_art(self) -> None:
        self.assertIsNone(obj=self.vault.catalog)
        self.vault.prune_art(items=[], art_dir=self.vault.art_dir)
        self.assertEqual(first=self.vault.art_dir.name, second="_none")
        self.assertFalse(expr=(self.folder / "covers" / "_none").exists())
        self.assertFalse(expr=(self.folder / ".catalogs" / "_none.covers.json").exists())

    def test_a_real_catalog_still_gets_its_art_folder(self) -> None:
        art_dir = self.folder / "covers" / "real"
        self.vault.prune_art(items=[], art_dir=art_dir)
        self.assertTrue(expr=art_dir.is_dir())
