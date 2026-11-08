import json
from unittest import mock

from nx_desk import config as settings
from nx_desk import names, net, vault
from tests.download.case import DownloadCase
from tests.helpers import TITLE, mod


class NameTests(DownloadCase):
    def test_update_title_uses_the_base_game_name(self) -> None:
        self.assertEqual(names.title_name(names={"0100BA4026E94000": "Game"}, title="0100BA4026E94800"), "Game")

    def test_downloads_use_the_title_database_name(self) -> None:
        self.store.titles = {TITLE: "Real Game™"}
        item = self.store._named(items=[mod(name="Catalog Name")])[0]
        self.assertEqual((item.name, item.catalog_name), ("Real Game", "Catalog Name"))

    def test_unknown_title_keeps_the_catalog_name(self) -> None:
        item = self.store._named(items=[mod(name="Catalog Name")])[0]
        self.assertEqual(item.name, "Catalog Name")

    def test_refresh_renames_loaded_games(self) -> None:
        self.store.items = [mod(name="Catalog Name")]

        with mock.patch.object(self.store, "title_names", return_value={TITLE: "Real"}):
            self.store.refresh_titles()

        self.assertEqual(self.store.items[0].name, "Real")

    def test_destination_still_finds_a_save_under_the_catalog_name(self) -> None:
        self.store.set_download_dir(text=str(self.base / "mine"))
        item = mod(name="Catalog Name", sha256="a" * 64)
        old = self.store.root / "Catalog Name - [VI]" / "[miss-unreviewed] [VI].zip"
        old.parent.mkdir(parents=True)
        old.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=old)
        self.store.titles = {TITLE: "Real Name"}
        named = self.store._named(items=[item])[0]
        self.assertEqual(self.store.status_of(entry=named), "ok")
        new = self.store.root / "Real Name - [VI]" / "[miss-unreviewed] [VI].zip"
        new.parent.mkdir(parents=True)
        new.write_bytes(data=b"zip")
        self.store._commit(entry=named, target=new)
        self.assertFalse(old.parent.exists())

    def test_game_names_lose_special_characters(self) -> None:
        for raw, expected in (
            ("One Piece: Grand Gourmet", "One Piece Grand Gourmet"),
            ("Castlevania: Belmont's Curse", "Castlevania Belmonts Curse"),
            ("Fate/Stay Night", "Fate Stay Night"),
            ("Ori & the Blind Forest", "Ori the Blind Forest"),
            ("Mario Kart™ 8 Deluxe!", "Mario Kart 8 Deluxe"),
            ("Spider-Man", "Spider-Man"),
            ("Trò Chơi Việt", "Tro Choi Viet"),
            ("Pokémon Legends Z-A", "Pokemon Legends Z-A"),
            ("ドラゴンクエスト", "ドラゴンクエスト"),
            ("!!!", "!!!"),
        ):
            self.assertEqual(names.clean_game_name(name=raw), expected)

    def test_all_capitals_names_become_title_case(self) -> None:
        for raw, expected in (
            ("OCTOPATH TRAVELER 0", "Octopath Traveler 0"),
            ("SPIDER-MAN", "Spider-Man"),
            ("FINAL FANTASY VII", "Final Fantasy VII"),
            ("ĐẠI CHIẾN", "Dai Chien"),
            ("SUPER MARIO 3D WORLD", "Super Mario 3D World"),
            ("Mario KART 8", "Mario KART 8"),
            ("ドラゴン", "ドラゴン"),
            (TITLE, TITLE),
            (f"PACK {TITLE}", f"Pack {TITLE}"),
        ):
            self.assertEqual(names.clean_game_name(name=raw), expected)

    def test_finds_a_save_from_before_accents_were_removed(self) -> None:
        self.store.set_download_dir(text=str(self.base / "mine"))
        item = mod(name="Pokémon Game", sha256="a" * 64)
        old = self.store.root / "Pokémon Game - [VI]" / "[miss-unreviewed] [VI].zip"
        old.parent.mkdir(parents=True)
        old.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=old)
        self.assertEqual(self.store.status_of(entry=item), "ok")

    def test_finds_and_replaces_a_save_from_before_names_were_cleaned(self) -> None:
        self.store.set_download_dir(text=str(self.base / "mine"))
        item = mod(name="Castlevania: Belmont's Curse", sha256="a" * 64)
        old = self.store.root / "Castlevania Belmont's Curse - [VI]" / "[miss-unreviewed] [VI].zip"
        old.parent.mkdir(parents=True)
        old.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=old)
        self.assertEqual(self.store.status_of(entry=item), "ok")
        new = self.store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
        new.parent.mkdir(parents=True)
        new.write_bytes(data=b"zip")
        self.store._commit(entry=item, target=new)
        self.assertFalse(old.parent.exists())

    def load_names(self, data: object) -> dict[str, str]:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(obj=data).encode()
        config = {settings.TITLE_IDS_KEY: "https://x.test/title-ids.json"}

        with (
            mock.patch.object(settings, "load_config", return_value=config),
            mock.patch.object(net, "http_get", return_value=response),
        ):
            return self.store.title_names()

    def test_names_come_from_the_games_of_the_title_id_list(self) -> None:
        data = {"games": {TITLE: "Game"}, "system": {"0100000000001000": {"name": "qlaunch", "group": "Applets"}}}
        self.assertEqual(self.load_names(data=data), {TITLE: "Game"})

    def test_a_saved_list_names_games_at_once(self) -> None:
        self.load_names(data={"games": {TITLE: "Game"}})
        self.assertEqual(vault.Vault(base=self.base / "data").titles, {TITLE: "Game"})

    def test_without_a_list_games_keep_their_catalog_names(self) -> None:
        with mock.patch.object(settings, "load_config", return_value={}):
            self.assertEqual(self.store.title_names(), {})
