import json

from nx_desk import vault
from tests.download.case import DownloadCase
from tests.helpers import job, mod


class DestinationTests(DownloadCase):
    def test_blank_download_folder_means_the_default(self) -> None:
        self.store.set_download_dir(text=str(self.base / "mine"))
        self.store.set_download_dir(text="  ")
        self.assertEqual(self.store.root, self.base / "data" / "downloaded" / "_none")

    def test_destination_decides_the_status(self) -> None:
        item = self.destination_item()
        self.assertEqual(self.store.status_of(entry=item), "missing")
        target = self.place(item=item)
        self.store._commit(entry=item, target=target)
        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertEqual(self.store.status_of(entry=item.model_copy(update={"sha256": "b" * 64})), "update")
        self.store.set_download_dir(text=str(self.base / "other"))
        self.assertEqual(self.store.status_of(entry=item), "missing")

    def test_destination_finds_a_moved_copy_after_a_game_version_change(self) -> None:
        item = self.destination_item()
        self.store._commit(entry=item, target=self.place(item=item))
        self.assertEqual(
            self.store.status_of(entry=item.model_copy(update={"sha256": "b" * 64, "game_version": "2.0"})),
            "update",
        )

    def test_hand_copied_file_is_judged_by_its_name(self) -> None:
        item = self.destination_item()
        self.place(item=item)
        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertEqual(self.store.status_of(entry=item.model_copy(update={"game_version": "2.0"})), "update")

    def test_default_folder_works_like_a_destination(self) -> None:
        item = mod(name="Game", sha256="a" * 64, game_version="1.0")
        self.assertEqual(self.store.status_of(entry=item), "missing")
        target = self.place(item=item)
        self.store._commit(entry=item, target=target)
        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertEqual(self.store.status_of(entry=item.model_copy(update={"sha256": "b" * 64})), "update")
        target.unlink()
        self.assertEqual(self.store.status_of(entry=item), "missing")

    def test_state_does_not_store_a_location(self) -> None:
        item = self.destination_item()
        self.store._commit(entry=item, target=self.place(item=item))
        self.assertNotIn("root", self.store.state[item.id])

    def test_status_ignores_a_root_left_by_an_older_version(self) -> None:
        item = self.destination_item()
        self.store._commit(entry=item, target=self.place(item=item))
        # Older versions stored a root, which the schema no longer has and so drops on reading.
        state = json.loads(s=self.store.state_path.read_text(encoding="utf-8"))
        state[item.id]["root"] = str(self.base / "gone")
        self.store.state_path.write_text(data=json.dumps(obj=state), encoding="utf-8")
        self.store._use_catalog(catalog=None)
        self.assertEqual(self.store.status_of(entry=item), "ok")

    def test_new_destination_leaves_the_old_copy_alone(self) -> None:
        item = self.destination_item()
        first = self.place(item=item)
        self.store._commit(entry=item, target=first)
        self.store.set_download_dir(text=str(self.base / "other"))
        self.store._commit(entry=item, target=self.place(item=item))
        self.assertTrue(first.exists())

    def test_update_inside_a_destination_replaces_the_old_copy(self) -> None:
        item = self.destination_item()
        first = self.place(item=item)
        self.store._commit(entry=item, target=first)
        self.store._commit(entry=item, target=self.place(item=item, name="[2.0-unreviewed] [VI].zip"))
        self.assertFalse(first.exists())

    def test_download_folder_stays_put_while_downloading(self) -> None:
        self.store.jobs["game"] = job(phase="downloading")
        before = self.store.root
        self.store.set_download_dir(text=str(self.base / "mine"))
        self.assertEqual(self.store.root, before)

    def test_move_download_dir_relocates_files_and_setting(self) -> None:
        self.store.set_download_dir(text=str(self.base / "old"))
        target = self.store.root / "Game - [VI] - [1.0]" / "Game - [VI] - [1.0].zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store.move_download_dir(new_dir=str(self.base / "new"))
        self.assertEqual(self.store.download_dir, str(self.base / "new"))
        self.assertTrue((self.base / "new" / "_none" / "Game - [VI] - [1.0]" / "Game - [VI] - [1.0].zip").is_file())
        self.assertFalse((self.base / "old" / "_none").exists())

    def test_move_refuses_a_clash(self) -> None:
        self.store.set_download_dir(text=str(self.base / "old"))
        (self.store.root).mkdir(parents=True)
        (self.base / "new" / "_none").mkdir(parents=True)

        with self.assertRaises(ValueError):
            self.store.move_download_dir(new_dir=str(self.base / "new"))

        self.assertEqual(self.store.download_dir, str(self.base / "old"))

    def test_move_to_the_same_folder_is_a_noop(self) -> None:
        self.store.set_download_dir(text=str(self.base / "here"))
        self.assertEqual(self.store.move_download_dir(new_dir=str(self.base / "here")), str(self.base / "here"))

    def test_saves_the_download_folder(self) -> None:
        self.store.set_download_dir(text=str(self.base / "mine"))
        again = vault.Vault(base=self.base / "data")
        self.assertEqual(again.download_dir, str(self.base / "mine"))
        self.assertEqual(again.root, self.base / "mine" / "_none")
