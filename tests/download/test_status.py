import tempfile
import unittest

from nx_desk import names, vault
from nx_desk.schemas.state import DownloadRecord, ReleaseRecord
from tests.helpers import mod


class ReplaceDownloadTests(unittest.TestCase):
    def test_saving_survives_an_old_folder_that_is_already_gone(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            item = mod(name="Game", sha256="a" * 64)
            store.state[item.id] = DownloadRecord(
                file="Game - []/old.zip",
                sha256="b" * 64,
                version="",
                downloaded_at="",
            )
            target = store.root / "elsewhere" / "new.zip"
            target.parent.mkdir(parents=True)
            target.write_bytes(data=b"zip")
            store._commit(entry=item, target=target)
            self.assertEqual(first=store.state[item.id].sha256, second="a" * 64)


class StatusTests(unittest.TestCase):
    def test_update_detection_uses_original_hash(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            store.set_mod_name(name="VI")
            item = mod()
            self.assertEqual(first=store.status_of(entry=item), second="missing")
            target = store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
            target.parent.mkdir(parents=True)
            target.write_bytes(data=b"repacked")
            store._commit(entry=item, target=target)
            self.assertEqual(first=store.status_of(entry=item), second="ok")
            self.assertEqual(first=store.status_of(entry=item.model_copy(update={"sha256": "1" * 64})), second="update")
            target.unlink()
            self.assertEqual(first=store.status_of(entry=item), second="missing")


class SavedGameVersionTests(unittest.TestCase):
    def test_folder_names_give_their_game_version(self) -> None:
        self.assertEqual(first=names.folder_version(folder="Game - [VI] - [1.0.2]"), second="1.0.2")
        self.assertEqual(first=names.folder_version(folder="Game - [VI]"), second="")
        self.assertEqual(first=names.folder_version(folder=""), second="")

    def test_a_record_gives_its_game_version_or_its_folder_does(self) -> None:
        saved = vault.Vault._saved_game_version
        self.assertEqual(first=saved(record=ReleaseRecord(game_version="1.1", folder="G - [VI] - [1.0]")), second="1.1")
        self.assertEqual(first=saved(record=ReleaseRecord(folder="G - [VI] - [1.0]")), second="1.0")
        self.assertEqual(first=saved(record=DownloadRecord(file="G - [VI] - [1.0]/G - [VI] - [1.0].zip")), second="1.0")

        self.assertEqual(first=saved(record=DownloadRecord()), second="")

    def test_a_download_records_its_game_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            item = mod(game_version="1.0.2")
            target = store.root / names.download_path(name=item.name, version=item.game_version, mod="VI")
            target.parent.mkdir(parents=True)
            target.write_bytes(data=b"zip")
            store.items = [item]
            store._commit(entry=item, target=target)
            self.assertEqual(first=store.state[item.id].game_version, second="1.0.2")

            self.assertEqual(first=store.snapshot().items[0].local_game_version, second="1.0.2")
