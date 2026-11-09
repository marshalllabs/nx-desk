import tempfile
import unittest

from nx_desk import config as settings
from nx_desk import names, vault
from nx_desk.catalog.parse import normalize, parse_catalog
from nx_desk.catalog.values import clean_mapping
from tests.helpers import TITLE, entry, mod, normal


class CatalogTests(unittest.TestCase):
    def test_rejects_unsafe_entries(self) -> None:
        self.assertIsNone(obj=normalize(raw=entry(id="../x")))
        self.assertIsNone(obj=normalize(raw=entry(url="http://example.com/a.zip")))
        # A bad or missing hash no longer rejects the entry; verification simply degrades.
        self.assertEqual(first=mod(sha256="abc").sha256, second="")

    def test_resolves_gdrive_mirrors(self) -> None:
        item = mod(mirrors=["gdrive:abcdefghij1234"])
        self.assertEqual(first=item.urls[1], second=settings.GDRIVE_URL + "abcdefghij1234")

    def test_target_path_uses_the_vault_format(self) -> None:
        item = mod(name="One: Two/Three", game_version="1.0.6 (kèm DLC)")
        path = names.download_path(name=item.name, version=item.game_version, mod="Bản A")
        self.assertEqual(
            first=path.as_posix(),
            second="One Two Three - [Bản A] - [1.0.6]/One Two Three - [Bản A] - [1.0.6].zip",
        )

    def test_missing_game_version(self) -> None:
        item = mod()
        self.assertEqual(
            first=names.download_path(name=item.name, version=item.game_version, mod="VI").name,
            second="Game - [VI] - [Miss].zip",
        )


class ArtworkTests(unittest.TestCase):
    def test_file_names_come_from_the_game_name(self) -> None:
        cases = {
            "Castlevania: Belmont's Curse": "castlevania-belmonts-curse",
            "Demon Slayer -Kimetsu no Yaiba- The Hinokami Chronicles": "demon-slayer-kimetsu-no-yaiba-the-hinokami-chronicles",
            "Pokémon Đỏ": "pokemon-do",
        }

        for name, slug in cases.items():
            self.assertEqual(first=names.art_slug(name=name), second=slug)

    def test_file_name_has_kind_and_a_safe_extension(self) -> None:
        item = mod(id="a", name="Game One", cover="https://x.test/a/c.JPG?v=1", background="https://x.test/b")
        # The stem, a digest of the URL, and the extension the URL gives.
        self.assertEqual(
            first=names.art_file_name(item=item, kind="cover", url=item.cover),
            second="game-one-cover.fa3c4f20.jpg",
        )
        self.assertEqual(
            first=names.art_file_name(item=item, kind="background", url=item.background),
            second="game-one-background.8173517f.img",
        )

    def test_another_url_gives_another_name_and_the_same_url_the_same(self) -> None:
        item = mod(id="a", name="Game One")
        first = names.art_file_name(item=item, kind="cover", url="https://x.test/one.png")
        self.assertEqual(first=first, second=names.art_file_name(item=item, kind="cover", url="https://x.test/one.png"))
        self.assertNotEqual(
            first=first,
            second=names.art_file_name(item=item, kind="cover", url="https://x.test/two.png"),
        )
        self.assertEqual(first=names.art_stem_of(file_name=first), second="game-one-cover")

    def test_file_name_falls_back_to_the_id(self) -> None:
        item = mod(id="a", name="???", cover="https://x.test/c.png")
        self.assertEqual(
            first=names.art_file_name(item=item, kind="cover", url=item.cover),
            second="a-cover.1ba75ac3.png",
        )


class FlexibleCatalogTests(unittest.TestCase):
    def test_heuristic_reads_alternative_keys(self) -> None:
        raw = {
            "games": [
                {"title": "Trò Chơi", "download": "https://x.test/a.zip", "phien_ban": "1.2", "the_loai": ["RPG"]},
            ],
        }
        item = parse_catalog(data=raw).items[0]
        self.assertEqual(first=item.name, second="Trò Chơi")
        self.assertEqual(first=item.urls, second=["https://x.test/a.zip"])
        self.assertEqual(first=item.version, second="1.2")
        self.assertEqual(first=item.tags, second=["RPG"])
        self.assertEqual(first=item.id, second="tro-choi")  # derived from the name when no id is given

    def test_top_level_list_is_a_catalog(self) -> None:
        self.assertEqual(first=len(parse_catalog(data=[{"name": "A", "url": "https://x.test/a.zip"}]).items), second=1)

    def test_nested_file_fields(self) -> None:
        raw = {
            "mods": [
                {"id": "g", "name": "G", "files": [{"url": "https://x.test/a.zip", "sha256": "a" * 64, "size": 10}]},
            ],
        }
        item = parse_catalog(data=raw).items[0]
        self.assertEqual(first=(item.urls, item.sha256, item.size), second=(["https://x.test/a.zip"], "a" * 64, 10))

    def test_manual_mapping_overrides_everything(self) -> None:
        raw = {"payload": [{"slug": "pack1", "tenGame": "Game", "tai": "https://x.test/a.zip"}]}
        mapping = {"__root__": "payload", "id": "slug", "name": "tenGame", "url": "tai"}
        item = parse_catalog(data=raw, mapping=mapping).items[0]
        self.assertEqual(first=(item.id, item.name, item.urls), second=("pack1", "Game", ["https://x.test/a.zip"]))

    def test_size_accepts_a_formatted_string(self) -> None:
        self.assertEqual(
            first=normal(raw={"id": "g", "url": "https://x.test/a.zip", "size": "1,234"}).size,
            second=1234,
        )

    def test_optional_fields_default_safely(self) -> None:
        item = normal(raw={"id": "g", "url": "https://x.test/a.zip"})
        self.assertEqual(first=(item.sha256, item.size, item.title_id), second=("", 0, ""))

    def test_clean_mapping_drops_blanks(self) -> None:
        self.assertEqual(first=clean_mapping(mapping={"id": " slug ", "name": "", "url": None}), second={"id": "slug"})


class VersionFallbackTests(unittest.TestCase):
    def test_update_detection_falls_back_to_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            store.set_mod_name(name="VI")
            item = normal(
                raw={"id": "g", "name": "G", "url": "https://x.test/a.zip", "mod_version": "1.0", "title_id": TITLE},
            )
            target = store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
            target.parent.mkdir(parents=True)
            target.write_bytes(data=b"zip")
            store._commit(entry=item, target=target)
            self.assertEqual(first=store.status_of(entry=item), second="ok")
            self.assertEqual(first=store.status_of(entry=item.model_copy(update={"version": "1.1"})), second="update")
