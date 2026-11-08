import json
from unittest import mock

from nx_desk import uploader, vault
from nx_desk.schemas.state import ReleaseRecord, ReleaseState
from tests.auto_upload.case import AutoUploadCase
from tests.helpers import mod


class ReleaseUploadTests(AutoUploadCase):
    def test_a_saved_mod_goes_to_the_release_named_after_the_catalog_folder(self) -> None:
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.assertIn("my-catalog", self.hub.releases)
        self.assertEqual(sorted(self.hub.assets), ["Game-VI-1-0.zip", "state.json"])
        text = "\n".join(line[3] for line in self.store.snapshot().log)
        self.assertIn("created release my-catalog", text)
        self.assertIn("uploaded to release my-catalog", text)

    def test_an_update_replaces_the_old_version_on_the_release(self) -> None:
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.download(item=mod(name="Game", sha256="", game_version="2.0"))
        self.assertEqual(sorted(self.hub.assets), ["Game-VI-2-0.zip", "state.json"])
        self.assertEqual(self.remote_state()["game"]["files"], ["Game-VI-2-0.zip"])

    def test_files_left_by_a_stopped_upload_are_removed(self) -> None:
        self.hub.releases.append("my-catalog")
        self.hub.add(name="uploading-Game-VI-1-0.zip.002", digest="sha256:x")
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.assertEqual(sorted(self.hub.assets), ["Game-VI-1-0.zip", "state.json"])

    def test_uses_its_own_repository_not_the_github_tab(self) -> None:
        self.store.set_upload_settings(source="", repo="me/other", tag="")
        calls: list[tuple[str, ...]] = []
        real = self.hub.__call__

        def spy(*args: str) -> str:
            calls.append(args)

            return real(*args)

        with mock.patch.object(uploader.command, "gh", spy):
            self.download(item=mod(name="Game", sha256="", game_version="1.0"))

        used = {arg for call in calls for arg in call if arg in ("me/mods", "me/other")}
        self.assertEqual(used, {"me/mods"})

    def test_a_state_read_from_another_repository_is_not_cached(self) -> None:
        data: ReleaseState = ReleaseState(repo="me/other", tag="my-catalog", digest="", mods={"game": ReleaseRecord()})
        self.store._keep_release_state(tag="my-catalog", data=data)
        self.assertEqual(self.store.release_state, ReleaseState())
        self.assertFalse(self.store._release_cache(folder="my-catalog").exists())

    def test_the_auto_repository_starts_from_the_github_tab_setting(self) -> None:
        registry = json.loads(s=self.store.registry_path.read_text(encoding="utf-8"))
        del registry["auto_repo"]
        self.store.registry_path.write_text(data=json.dumps(obj=registry), encoding="utf-8")
        self.assertEqual(vault.Vault(base=self.base / "data").auto_repo, "me/mods")

    def test_nothing_is_uploaded_when_the_box_is_off(self) -> None:
        self.store.set_auto_upload(enabled=False)
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.assertEqual(self.hub.assets, {})

    def test_without_a_repository_the_mod_stays_on_disk_and_nothing_fails(self) -> None:
        self.store.set_auto_repo(repo="")
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.assertEqual(self.hub.assets, {})
        self.assertEqual(self.store.snapshot().batch.upload_failed, 0)

    def test_gh_signed_out_skips_the_upload(self) -> None:
        self.store.gh_ready = False
        self.download(item=mod(name="Game", sha256="", game_version="1.0"))
        self.assertEqual(self.hub.assets, {})
