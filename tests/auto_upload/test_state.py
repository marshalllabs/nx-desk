import hashlib
import json
from pathlib import Path
from typing import Optional
from unittest import mock

from nx_desk import names, uploader, vault
from nx_desk.schemas.common import Progress, Report
from nx_desk.schemas.github import FolderRef
from nx_desk.schemas.release_state import ReleaseDocument
from nx_desk.utils.callbacks import quiet
from tests.auto_upload.case import AutoUploadCase
from tests.helpers import mod


class StateTests(AutoUploadCase):
    def test_manual_upload_keeps_game_version_for_every_shared_file_id(self) -> None:
        self.store.set_auto_upload(enabled=False)
        first, _second = self.store._named(
            items=[
                mod(id="first", name="Shared Game", sha256="a" * 64, game_version="Update 1.0.2"),
                mod(id="second", name="Shared Game Alias", sha256="a" * 64, game_version="Update 1.0.2"),
            ],
        )
        self.download(item=first)
        self.hub.releases.append("my-catalog")
        self.github_tab()
        folder = self.store.local_path(record=self.store.state[first.id])
        assert folder is not None
        self.store.upload_folders(names=[folder.parent.name])
        records = self.remote_state()
        self.assertEqual(first=set(records), second={"first", "second"})
        self.assertEqual(first=records["first"].game_version, second="Update 1.0.2")
        self.assertEqual(first=records["second"].game_version, second="Update 1.0.2")
        self.assertEqual(first=records["first"].files, second=records["second"].files)

    def test_next_state_write_repairs_missing_metadata_without_uploading_the_mod(self) -> None:
        item = self.item()
        self.download(item=item)
        original = self.remote_state()[item.id]
        body = ReleaseDocument.model_validate_json(json_data=self.hub.blobs["state.json"])
        data = body.model_dump_json(exclude={"mods": {item.id: {"game_version"}}}).encode()
        self.hub.blobs["state.json"] = data
        self.hub.assets["state.json"].digest = f"sha256:{hashlib.sha256(string=data).hexdigest()}"
        blobs = {name: blob for name, blob in self.hub.blobs.items() if name != "state.json"}

        with self.store.github_lock:
            self.store._write_release_state(repo="me/mods", tag="my-catalog", change=lambda mods, assets: None)

        repaired = self.remote_state()[item.id]
        self.assertEqual(first=repaired.game_version, second=item.game_version)
        self.assertEqual(first=repaired.uploaded_at, second=original.uploaded_at)
        self.assertEqual(first=repaired.folder, second=original.folder)
        self.assertEqual(first=repaired.files, second=original.files)
        self.assertEqual(
            first={name: blob for name, blob in self.hub.blobs.items() if name != "state.json"},
            second=blobs,
        )

    def test_invalid_remote_state_is_not_overwritten(self) -> None:
        self.download(item=self.item())
        data = b'{"mods":null}'
        self.hub.blobs["state.json"] = data
        self.hub.assets["state.json"].digest = f"sha256:{hashlib.sha256(string=data).hexdigest()}"

        with self.store.github_lock, self.assertRaises(expected_exception=uploader.command.GitHubError):
            self.store._write_release_state(repo="me/mods", tag="my-catalog", change=lambda mods, assets: None)

        self.assertEqual(first=self.hub.blobs["state.json"], second=data)

    def test_state_json_records_the_original_sha256(self) -> None:
        self.download(item=self.item())
        record = self.remote_state()["game"]
        self.assertEqual(first=(record.sha256, record.folder), second=("a" * 64, "Game - [VI] - [1.0]"))
        self.assertEqual(first=record.files, second=["Game-VI-1-0.zip"])
        self.assertEqual(first=json.loads(s=self.hub.blobs["state.json"])["catalog"], second="https://x.test/c.json")

    def test_one_upload_is_recorded_for_every_entry_of_the_file(self) -> None:
        self.store.set_auto_delete(enabled=True)
        first, second = self.store._named(
            items=[mod(id="x", name="Game X", sha256="a" * 64), mod(id="x2", name="Game X-2", sha256="a" * 64)],
        )
        self.download(item=first)
        mods = self.remote_state()
        self.assertEqual(first=mods["x"], second=mods["x2"].model_copy(update={"uploaded_at": mods["x"].uploaded_at}))
        self.assertEqual(first=self.store.status_of(entry=second), second="ok")

    def test_deleting_after_upload_moves_the_status_to_the_release(self) -> None:
        self.store.set_auto_delete(enabled=True)
        item = self.item()
        self.download(item=item)
        self.assertFalse(expr=(self.store.root / "Game - [VI] - [1.0]").exists())
        self.assertEqual(first=self.store.status_of(entry=item), second="ok")
        self.assertTrue(expr=self.store.snapshot().items[0].remote)
        self.assertEqual(first=self.store.status_of(entry=self.item(sha="b")), second="update")
        self.store.set_auto_delete(enabled=False)
        self.assertEqual(first=self.store.status_of(entry=item), second="missing")

    def test_a_failed_state_write_keeps_the_local_copy(self) -> None:
        self.store.set_auto_delete(enabled=True)

        with mock.patch.object(
            target=uploader.state,
            attribute="replace_asset",
            side_effect=uploader.command.GitHubError("boom"),
        ):
            self.download(item=self.item())

        self.assertTrue(expr=(self.store.root / "Game - [VI] - [1.0]").is_dir())

    def test_turning_upload_off_turns_delete_off(self) -> None:
        self.store.set_auto_delete(enabled=True)
        self.store.set_auto_upload(enabled=False)
        self.assertFalse(expr=self.store.auto_delete)
        self.store.set_auto_delete(enabled=True)
        self.assertFalse(expr=self.store.auto_delete)

    def test_mods_uploaded_before_state_json_are_seeded(self) -> None:
        older = mod(id="old", name="Old", sha256="c" * 64, game_version="1.0")
        target = self.store.root / names.download_path(name="Old", version="1.0", mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=older, target=target)
        self.hub.releases.append("my-catalog")
        self.hub.add(name="Old-VI-1-0.zip", digest="sha256:x")
        self.hub.assets["Old-VI-1-0.zip"].updated_at = "2999-01-01T00:00:00Z"
        self.download(item=self.item())
        self.assertEqual(first=sorted(self.remote_state()), second=["game", "old"])
        self.assertEqual(first=self.remote_state()["old"].sha256, second="c" * 64)

    def test_an_upload_older_than_the_download_is_not_trusted(self) -> None:
        older = mod(id="old", name="Old", sha256="c" * 64, game_version="1.0")
        target = self.store.root / names.download_path(name="Old", version="1.0", mod="VI")
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=older, target=target)
        self.hub.releases.append("my-catalog")
        self.hub.add(name="Old-VI-1-0.zip", digest="sha256:x")
        self.hub.assets["Old-VI-1-0.zip"].updated_at = "2000-01-01T00:00:00Z"
        self.download(item=self.item())
        self.assertEqual(first=sorted(self.remote_state()), second=["game"])

    def test_entries_already_in_state_json_are_not_replaced(self) -> None:
        self.download(item=self.item())
        self.store.state["game"].sha256 = "f" * 64
        self.store._write_json(path=self.store.state_path, value=self.store.state)
        self.github_tab()
        self.store.delete_release_assets(names=[])

        with self.store.github_lock:
            self.store._write_release_state(repo="me/mods", tag="my-catalog", change=lambda mods, assets: None)

        self.assertEqual(first=self.remote_state()["game"].sha256, second="a" * 64)

    def test_an_upload_cut_off_midway_keeps_what_went_up(self) -> None:
        self.store.set_auto_upload(enabled=False)
        first = mod(id="one", name="One", sha256="1" * 64, game_version="1.0", size=1)
        second = mod(id="two", name="Two", sha256="2" * 64, game_version="1.0", size=2)
        self.download(item=first)
        self.download(item=second)
        self.hub.releases.append("my-catalog")
        self.github_tab()
        real = vault.Vault._upload_one

        def fail_second(
            store: vault.Vault,
            folder: FolderRef,
            repo: str,
            tag: str,
            stem: str,
            work: Path,
            report: Optional[Report] = None,
            moved: Progress = quiet,
            zipped: Progress = quiet,
        ) -> None:
            if folder.name.startswith("Two"):
                raise uploader.command.GitHubError("connection lost")

            return real(
                self=store,
                folder=folder,
                repo=repo,
                tag=tag,
                stem=stem,
                work=work,
                report=report,
                moved=moved,
                zipped=zipped,
            )

        with mock.patch.object(target=vault.Vault, attribute="_upload_one", new=fail_second):
            self.store.upload_folders(names=["One - [VI] - [1.0]", "Two - [VI] - [1.0]"])

        self.assertEqual(first=sorted(self.remote_state()), second=["one"])

    def test_refresh_reads_a_state_json_written_elsewhere(self) -> None:
        self.store.set_auto_delete(enabled=True)
        self.download(item=self.item())
        files = self.remote_state()["game"].files
        body = {"version": 1, "mods": {"game": {"sha256": "b" * 64, "version": "", "files": files}}}
        data = json.dumps(obj=body).encode()
        self.hub.blobs["state.json"] = data
        self.hub.assets["state.json"].digest = f"sha256:{hashlib.sha256(string=data).hexdigest()}"
        self.store.refresh_release_state()
        self.assertEqual(first=self.store.status_of(entry=self.item()), second="update")
