from unittest import mock

from nx_desk import names, vault
from nx_desk.schemas.catalog import Mod
from nx_desk.schemas.download import Fetched
from tests.download.case import DownloadCase
from tests.helpers import TITLE, mod


class SavedTests(DownloadCase):
    def test_mod_name_is_saved(self) -> None:
        self.store.set_mod_name(name="Bản A")
        self.assertEqual(vault.Vault(base=self.base / "data").mod_name, "Bản A")

    def test_download_path_repeats_the_folder_name_in_the_zip(self) -> None:
        path = names.download_path(name="Castlevania: Belmont's Curse", version="1.1.0", mod="VI")
        name = "Castlevania Belmonts Curse - [VI] - [1.1.0]"
        self.assertEqual(path.as_posix(), f"{name}/{name}.zip")
        self.assertEqual(names.download_path(name="Game", version="", mod="VI").name, "Game - [VI] - [Miss].zip")

    def test_new_game_version_shows_as_an_update_and_replaces_the_old_folder(self) -> None:
        item = mod(name="Game", sha256="a" * 64, game_version="1.0")
        old = self.save_download(item=item)
        newer: Mod = item.model_copy(update={"sha256": "b" * 64, "game_version": "1.1"})

        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertEqual(self.store.status_of(entry=newer), "update")
        self.save_download(item=newer)
        self.assertFalse(old.parent.exists())
        self.assertEqual(self.store.status_of(entry=newer), "ok")

    def test_other_games_with_a_similar_name_do_not_count(self) -> None:
        self.save_download(item=mod(name="Game II", sha256="a" * 64, game_version="1.0"))
        item = mod(id="g", name="Game", sha256="a" * 64, game_version="1.0")
        self.assertEqual(self.store.status_of(entry=item), "missing")

    def test_copied_download_is_judged_by_its_name(self) -> None:
        item = mod(name="Game", sha256="a" * 64, game_version="1.0")
        target = self.store.root / names.download_path(name="Game", version="1.0", mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertEqual(self.store.status_of(entry=item.model_copy(update={"game_version": "2.0"})), "update")

    def test_downloads_use_the_same_mod_name(self) -> None:
        self.zip_file(relative="Game.zip", members={f"{TITLE}/romfs/a.bin": b"1"})
        item = mod(name="Game", sha256="", game_version="1.0")
        self.store.items = [item]
        self.store.enqueue(ids=[item.id])

        with (
            mock.patch.object(self.store, "_download", return_value=Fetched(wire=self.src / "Game.zip")),
            mock.patch.object(self.store, "_commit", side_effect=SystemExit),
            self.assertRaises(SystemExit),
        ):
            self.store._run_download(*self.store.queue.get()[2:])
            self.store._repack_next()

        self.assertTrue((self.store.root / "Game - [VI] - [1.0]" / "Game - [VI] - [1.0].zip").exists())
