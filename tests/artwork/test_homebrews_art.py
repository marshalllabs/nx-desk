import json
from unittest import mock

from nx_desk import config, net
from nx_desk.schemas.artwork import ArtFiles
from nx_desk.schemas.homebrew import Homebrew
from nx_desk.schemas.port import Port
from nx_desk.vault.art_queue import ArtQueue
from tests.artwork.case import GRID, HERO, ArtCase, FakeSteamGridDB, Response


class HomebrewArtTests(ArtCase):
    def entry(self, name: str = "Game") -> Homebrew:
        return Homebrew(id=name.lower(), name=name, url=f"https://example.com/wiki/{name}")

    def queue(self) -> ArtQueue:
        return ArtQueue(vault=self.vault, art_dir=self.vault.homebrews_art_dir, port_cards=False)

    def test_cover_and_banner_use_the_homebrews_cache(self) -> None:
        self.vault.set_art_key(key="example-key")
        queue = self.queue()
        item = self.entry()
        fake = FakeSteamGridDB()

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            queue.fetch(item=item, version=queue.version)

        cover, banner = queue.files[item.id].cover, queue.files[item.id].background
        assert cover is not None and banner is not None
        self.assertEqual(first=cover.parent, second=self.folder / "covers" / "_homebrews")
        self.assertEqual(first=banner.parent, second=cover.parent)
        self.assertTrue(expr=cover.is_file() and banner.is_file())
        self.assertEqual(first=fake.images, second=[GRID, HERO])
        self.assertFalse(expr=self.vault.ports_art_dir.exists())

    def test_without_a_key_no_requests_are_made(self) -> None:
        queue = self.queue()
        item = self.entry()

        with mock.patch.object(target=net, attribute="http_get") as request:
            queue.want(items=[item])

        request.assert_not_called()
        self.assertTrue(expr=queue.needs_key())
        self.assertTrue(expr=queue.settled(item=item))

    def test_missing_art_is_cached_without_fetching_the_source_page(self) -> None:
        self.vault.set_art_key(key="example-key")
        item = self.entry()
        queue = self.queue()
        fake = FakeSteamGridDB(games={})

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            queue.fetch(item=item, version=queue.version)
            queue.fetch(item=item, version=queue.version)

        self.assertEqual(first=len(fake.calls), second=1)
        self.assertEqual(first=fake.images, second=[])
        self.assertEqual(first=queue.files[item.id], second=ArtFiles())
        self.assertTrue(expr=queue.settled(item=item))

    def test_lookup_and_image_files_survive_a_new_queue(self) -> None:
        self.vault.set_art_key(key="example-key")
        item = self.entry()
        fake = FakeSteamGridDB()
        queue = self.queue()

        with mock.patch.object(target=net, attribute="http_get", side_effect=fake):
            queue.fetch(item=item, version=queue.version)
            before = (len(fake.calls), len(fake.images))
            again = self.queue()
            again.fetch(item=item, version=again.version)

        self.assertEqual(first=before, second=(len(fake.calls), len(fake.images)))
        self.assertEqual(first=again.files[item.id], second=queue.files[item.id])

    def test_rate_limited_lookup_is_left_for_retry(self) -> None:
        self.vault.set_art_key(key="example-key")
        item = self.entry()
        queue = self.queue()
        queue.asked.add(item.id)

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB(refuse=429)):
            queue.fetch(item=item, version=queue.version)

        self.assertNotIn(member=item.id, container=queue.asked)
        self.assertNotIn(member=item.id, container=queue.files)
        self.assertGreater(a=self.vault.art_paused_until, b=0)

    def test_key_changes_discard_old_results(self) -> None:
        self.vault.set_art_key(key="example-key")
        queue = self.queue()

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB()):
            queue.fetch(item=self.entry(), version=queue.version)

        self.vault.set_art_key(key="replacement-key")
        queue.check_key()
        self.assertEqual(first=queue.files, second={})
        self.assertEqual(first=queue.asked, second=set())

    def test_refresh_prunes_removed_homebrews_without_touching_ports(self) -> None:
        old, kept = self.entry(name="Old"), self.entry()
        port = Port(id="port", name="Game", platform="Other")

        with mock.patch.object(target=net, attribute="http_get", side_effect=FakeSteamGridDB()):
            old_path = self.vault.fetch_art(item=old, kind="cover", url=GRID, art_dir=self.vault.homebrews_art_dir)
            kept_path = self.vault.fetch_art(item=kept, kind="cover", url=GRID, art_dir=self.vault.homebrews_art_dir)
            port_path = self.vault.fetch_art(item=port, kind="cover", url=GRID, art_dir=self.vault.ports_art_dir)

        assert old_path is not None and kept_path is not None and port_path is not None
        raw = json.dumps(obj={"homebrews": [kept.model_dump()]}).encode()

        with (
            mock.patch.object(
                target=config,
                attribute="load_config",
                return_value={config.HOMEBREWS_KEY: "https://example.com/feed"},
            ),
            mock.patch.object(
                target=net,
                attribute="http_get",
                return_value=Response(body=raw),
            ),
        ):
            self.vault.load_homebrews(force=True)

        self.assertEqual(first=self.vault.homebrew_error, second="")
        self.assertFalse(expr=old_path.exists())
        self.assertTrue(expr=kept_path.exists())
        self.assertTrue(expr=port_path.exists())
