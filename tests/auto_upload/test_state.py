import hashlib
import json
from typing import Any
from unittest import mock

from nx_desk import names, uploader, vault
from nx_desk.schemas.github import FolderRef
from tests.auto_upload.case import AutoUploadCase
from tests.helpers import mod


class StateTests(AutoUploadCase):
    def test_state_json_records_the_original_sha256(self) -> None:
        self.download(item=self.item())
        record = self.remote_state()["game"]
        self.assertEqual((record["sha256"], record["folder"]), ("a" * 64, "Game - [VI] - [1.0]"))
        self.assertEqual(record["files"], ["Game-VI-1-0.zip"])
        self.assertEqual(json.loads(s=self.hub.blobs["state.json"])["catalog"], "https://x.test/c.json")

    def test_one_upload_is_recorded_for_every_entry_of_the_file(self) -> None:
        self.store.set_auto_delete(enabled=True)
        first, second = self.store._named(
            items=[mod(id="x", name="Game X", sha256="a" * 64), mod(id="x2", name="Game X-2", sha256="a" * 64)],
        )
        self.download(item=first)
        mods = self.remote_state()
        self.assertEqual(mods["x"], {**mods["x2"], "uploaded_at": mods["x"]["uploaded_at"]})
        self.assertEqual(self.store.status_of(entry=second), "ok")

    def test_deleting_after_upload_moves_the_status_to_the_release(self) -> None:
        self.store.set_auto_delete(enabled=True)
        item = self.item()
        self.download(item=item)
        self.assertFalse((self.store.root / "Game - [VI] - [1.0]").exists())
        self.assertEqual(self.store.status_of(entry=item), "ok")
        self.assertTrue(self.store.snapshot().items[0].remote)
        self.assertEqual(self.store.status_of(entry=self.item(sha="b")), "update")
        self.store.set_auto_delete(enabled=False)
        self.assertEqual(self.store.status_of(entry=item), "missing")

    def test_a_failed_state_write_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)

        with mock.patch.object(uploader.state, "replace_asset", side_effect=uploader.command.GhError("boom")):
            self.download(item=self.item())

        self.assertTrue((self.store.root / "Game - [VI] - [1.0]").is_dir())

    def test_turning_upload_off_turns_delete_off(self) -> None:
        self.store.set_auto_delete(enabled=True)
        self.store.set_auto_upload(enabled=False)
        self.assertFalse(self.store.auto_delete)
        self.store.set_auto_delete(enabled=True)
        self.assertFalse(self.store.auto_delete)

    def test_mods_uploaded_before_state_json_are_seeded(self) -> None:
        older = mod(id="old", name="Old", sha256="c" * 64, game_version="1.0")
        target = self.store.root / names.download_path(name="Old", version="1.0", mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=older, target=target)
        self.hub.releases.append("my-catalog")
        self.hub.add(name="Old-VI-1-0.zip", digest="sha256:x")
        self.hub.assets["Old-VI-1-0.zip"]["updated_at"] = "2999-01-01T00:00:00Z"
        self.download(item=self.item())
        self.assertEqual(sorted(self.remote_state()), ["game", "old"])
        self.assertEqual(self.remote_state()["old"]["sha256"], "c" * 64)

    def test_an_upload_older_than_the_download_is_not_trusted(self) -> None:
        older = mod(id="old", name="Old", sha256="c" * 64, game_version="1.0")
        target = self.store.root / names.download_path(name="Old", version="1.0", mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=older, target=target)
        self.hub.releases.append("my-catalog")
        self.hub.add(name="Old-VI-1-0.zip", digest="sha256:x")
        self.hub.assets["Old-VI-1-0.zip"]["updated_at"] = "2000-01-01T00:00:00Z"
        self.download(item=self.item())
        self.assertEqual(sorted(self.remote_state()), ["game"])

    def test_entries_already_in_state_json_are_not_replaced(self) -> None:
        self.download(item=self.item())
        self.store.state["game"].sha256 = "f" * 64
        self.store._write_json(path=self.store.state_path, value=self.store.state)
        self.github_tab()
        self.store.delete_release_assets(names=[])

        with self.store.github_lock:
            self.store._write_release_state(repo="me/mods", tag="my-catalog", change=lambda mods, assets: None)

        self.assertEqual(self.remote_state()["game"]["sha256"], "a" * 64)

    def test_an_upload_cut_off_midway_keeps_what_went_up(self) -> None:
        self.store.set_auto_upload(enabled=False)
        first = mod(id="one", name="One", sha256="1" * 64, game_version="1.0", size=1)
        second = mod(id="two", name="Two", sha256="2" * 64, game_version="1.0", size=2)
        self.download(item=first)
        self.download(item=second)
        self.hub.releases.append("my-catalog")
        self.github_tab()
        real = vault.Vault._upload_one

        def fail_second(store: vault.Vault, folder: FolderRef, *args: Any, **kwargs: Any) -> None:
            if folder.name.startswith("Two"):
                raise uploader.command.GhError("connection lost")

            return real(store, folder, *args, **kwargs)

        with mock.patch.object(vault.Vault, "_upload_one", fail_second):
            self.store.upload_folders(names=["One - [VI] - [1.0]", "Two - [VI] - [1.0]"])

        self.assertEqual(sorted(self.remote_state()), ["one"])

    def test_refresh_reads_a_state_json_written_elsewhere(self) -> None:
        self.store.set_auto_delete(enabled=True)
        self.download(item=self.item())
        body = {"version": 1, "mods": {"game": {"sha256": "b" * 64, "version": "", "files": []}}}
        data = json.dumps(obj=body).encode()
        self.hub.blobs["state.json"] = data
        self.hub.assets["state.json"]["digest"] = f"sha256:{hashlib.sha256(data).hexdigest()}"
        self.store.refresh_release_state()
        self.assertEqual(self.store.status_of(entry=self.item()), "update")
