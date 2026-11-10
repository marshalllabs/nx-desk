import hashlib
import io
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from unittest import mock

from nx_desk import config as settings
from nx_desk import net, system, uploader, vault
from nx_desk.schemas.api import ReleasePayload
from nx_desk.schemas.update import AppAsset, AppUpdate, UpdateJob
from nx_desk.vault.app_update import parse_version


# An update whose asset holds these fields; None for a release without one for this platform.
def update_with(asset: Optional[Dict[str, object]]) -> AppUpdate:
    return AppUpdate.model_validate(obj={"tag": "v2.0.0", "url": "https://github.com/o/r", "asset": asset})


class AppUpdateTests(unittest.TestCase):
    URL = "https://example.com/latest"

    def check(self, current: str, body: bytes) -> Tuple[Optional[AppUpdate], mock.MagicMock]:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = body
        config = {settings.VERSION_KEY: current, "NX_DESK_RELEASES_URL": self.URL}

        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(target=settings, attribute="load_config", return_value=config),
            mock.patch.object(target=net, attribute="http_get", return_value=response) as get,
        ):
            store = vault.Vault(base=folder)
            store.check_app_update()

        return store.app_update, get

    def release(self, tag: str) -> bytes:
        return f'{{"tag_name": "{tag}", "html_url": "https://github.com/o/r/releases/tag/{tag}"}}'.encode()

    def test_picks_the_asset_for_this_platform(self) -> None:
        asset = {
            "name": system.asset_name(),
            "size": 5,
            "digest": "sha256:" + "a" * 64,
            "browser_download_url": "https://github.com/o/r/releases/download/v1/a.zip",
        }
        release = {"assets": [{"name": "other.zip"}, asset]}
        self.assertEqual(
            first=vault.Vault.pick_asset(release=ReleasePayload.model_validate(obj=release)),
            second=AppAsset(url="https://github.com/o/r/releases/download/v1/a.zip", size=5, sha256="a" * 64),
        )

    def test_rejects_assets_that_cannot_be_verified(self) -> None:
        good = {
            "name": system.asset_name(),
            "size": 5,
            "digest": "sha256:" + "a" * 64,
            "browser_download_url": "https://github.com/o/r/a.zip",
        }

        for change in (
            {"digest": None},
            {"digest": "md5:abc"},
            {"size": 0},
            {"size": settings.MAX_UPDATE + 1},
            {"browser_download_url": "https://evil.test/a.zip"},
        ):
            self.assertIsNone(
                obj=vault.Vault.pick_asset(release=ReleasePayload.model_validate(obj={"assets": [{**good, **change}]})),
            )

        self.assertIsNone(obj=vault.Vault.pick_asset(release=ReleasePayload.model_validate(obj={"assets": []})))

    def test_app_version(self) -> None:
        with mock.patch.object(target=settings, attribute="load_config", return_value={settings.VERSION_KEY: "v1.2.3"}):
            self.assertEqual(first=settings.app_version(), second="v1.2.3")

        with mock.patch.object(target=settings, attribute="load_config", return_value={settings.VERSION_KEY: ""}):
            self.assertEqual(first=settings.app_version(), second="dev")

    def test_reports_the_outcome_of_a_check(self) -> None:
        outcomes = {
            ("v1.0.0", self.release(tag="v1.0.1")): "available",
            ("v1.0.1", self.release(tag="v1.0.1")): "current",
            ("v1.0.0", b"not json"): "error",
            ("", self.release(tag="v1.0.1")): "unversioned",
        }

        for (current, body), outcome in outcomes.items():
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = body
            config = {settings.VERSION_KEY: current, "NX_DESK_RELEASES_URL": self.URL}

            with (
                tempfile.TemporaryDirectory() as folder,
                mock.patch.object(target=settings, attribute="load_config", return_value=config),
                mock.patch.object(target=net, attribute="http_get", return_value=response),
            ):
                self.assertEqual(first=vault.Vault(base=folder).check_app_update(), second=outcome)

    def test_parses_versions(self) -> None:
        self.assertEqual(first=parse_version(text="v1.2.3"), second=(1, 2, 3))

        for text in ("", "dev", "v1.2", "1.2.3-beta"):
            self.assertIsNone(obj=parse_version(text=text))

    def test_reports_a_newer_release(self) -> None:
        update, _ = self.check(current="v1.9.0", body=self.release(tag="v1.10.0"))
        assert update is not None
        self.assertEqual(first=update.tag, second="v1.10.0")

    def test_ignores_same_or_older_releases(self) -> None:
        for tag in ("v1.2.3", "v1.2.2"):
            self.assertIsNone(obj=self.check(current="v1.2.3", body=self.release(tag=tag))[0])

    def test_builds_without_a_version_never_ask(self) -> None:
        update, get = self.check(current="", body=self.release(tag="v9.0.0"))
        self.assertIsNone(obj=update)
        get.assert_not_called()

    def test_ignores_bad_responses(self) -> None:
        for body in (b"not json", b"{}", b"[]", b'{"tag_name": "v9.0.0", "html_url": "http://x.test"}'):
            self.assertIsNone(obj=self.check(current="v1.0.0", body=body)[0])

    def test_a_github_url_is_read_through_the_public_api(self) -> None:
        url = "https://api.github.com/repos/o/r/releases/latest"
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = self.release(tag="v2.0.0")
        config = {
            settings.VERSION_KEY: "v1.0.0",
            "NX_DESK_RELEASES_URL": url,
        }

        with (
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(target=settings, attribute="load_config", return_value=config),
            mock.patch.object(target=net, attribute="http_get", return_value=response) as get,
            mock.patch.object(target=uploader.api, attribute="request") as gh,
        ):
            self.assertEqual(first=vault.Vault(base=folder).check_app_update(), second="available")

        get.assert_called_once_with(url=url, headers={"Accept": "application/vnd.github+json"})
        gh.assert_not_called()


class SelfUpdateTests(unittest.TestCase):
    NAME = "NXDesk"

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.program = self.dir / self.NAME
        self.program.write_bytes(data=b"old program")
        self.data = self.dir / "downloaded" / "game.zip"
        self.data.parent.mkdir()
        self.data.write_bytes(data=b"my data")

    def release_zip(self, members: Optional[Dict[str, bytes]] = None) -> bytes:
        buffer = io.BytesIO()

        with zipfile.ZipFile(file=buffer, mode="w") as output:
            for name, content in (members or {self.NAME: b"new program", "downloaded/": b"", "covers/": b""}).items():
                output.writestr(zinfo_or_arcname=name, data=content)

        return buffer.getvalue()

    def install(self, body: bytes, asset: Optional[Dict[str, object]] = None) -> UpdateJob:
        digest = hashlib.sha256(string=body).hexdigest()
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(initial_bytes=body)
        fields = {"url": "https://github.com/a", "size": len(body), "sha256": digest, **(asset or {})}
        store = vault.Vault(base=self.dir)
        # A non-GitHub URL, so the download uses a plain request, not gh.
        config = {"NX_DESK_RELEASES_URL": "https://example.com/latest"}

        with (
            mock.patch.object(target=settings, attribute="load_config", return_value=config),
            mock.patch.object(target=net, attribute="http_get", return_value=response),
            mock.patch.object(target=system, attribute="program_path", return_value=self.program),
            mock.patch.object(target=sys, attribute="platform", new="linux"),
        ):
            store.install_app_update(update=update_with(asset=fields))

        job = store.app_update_job
        assert job is not None

        return job

    def test_replaces_the_program_and_keeps_data_and_a_backup(self) -> None:
        job = self.install(body=self.release_zip())
        self.assertEqual(first=job.phase, second="done")
        self.assertEqual(first=self.program.read_bytes(), second=b"new program")
        self.assertEqual(first=system.backup_path(program=self.program).read_bytes(), second=b"old program")
        self.assertEqual(first=self.data.read_bytes(), second=b"my data")

    def test_new_program_is_executable(self) -> None:
        self.install(body=self.release_zip())

        if sys.platform != "win32":
            self.assertTrue(expr=self.program.stat().st_mode & 0o100)

    def test_wrong_digest_changes_nothing(self) -> None:
        job = self.install(body=self.release_zip(), asset={"sha256": "0" * 64})
        self.assertEqual(first=job.phase, second="error")
        self.assertEqual(first=self.program.read_bytes(), second=b"old program")
        self.assertFalse(expr=system.backup_path(program=self.program).exists())

    def test_oversized_download_is_stopped(self) -> None:
        job = self.install(body=self.release_zip(), asset={"size": 3})
        self.assertEqual(first=job.phase, second="error")
        self.assertEqual(first=self.program.read_bytes(), second=b"old program")

    def test_zip_without_the_program_changes_nothing(self) -> None:
        job = self.install(body=self.release_zip(members={"covers/": b"", "other": b"x"}))
        self.assertEqual(first=job.phase, second="error")
        self.assertEqual(first=self.program.read_bytes(), second=b"old program")

    def test_failed_swap_restores_the_old_program(self) -> None:
        new = self.dir / "new"
        new.write_bytes(data=b"new")

        with (
            mock.patch.object(target=shutil, attribute="move", side_effect=OSError("disk full")),
            self.assertRaises(expected_exception=OSError),
        ):
            system.swap_program(new=new, program=self.program)

        self.assertEqual(first=self.program.read_bytes(), second=b"old program")

    def test_next_start_removes_the_backup(self) -> None:
        backup = system.backup_path(program=self.program)
        backup.write_bytes(data=b"old")

        with (
            mock.patch.object(target=sys, attribute="frozen", new=True, create=True),
            mock.patch.object(target=system, attribute="program_path", return_value=self.program),
        ):
            system.remove_old_program()

        self.assertFalse(expr=backup.exists())

    def test_work_files_are_removed(self) -> None:
        self.install(body=self.release_zip())
        self.assertFalse(expr=(self.dir / ".parts" / "app-update").exists())

    def test_a_github_release_asset_is_downloaded_over_http(self) -> None:
        body = self.release_zip()
        config = {"NX_DESK_RELEASES_URL": "https://api.github.com/repos/o/r/releases/latest"}
        response = mock.MagicMock()
        response.__enter__.return_value = io.BytesIO(initial_bytes=body)
        fields = {"url": "https://github.com/a", "size": len(body), "sha256": hashlib.sha256(string=body).hexdigest()}
        store = vault.Vault(base=self.dir)

        with (
            mock.patch.object(target=settings, attribute="load_config", return_value=config),
            mock.patch.object(target=net, attribute="http_get", return_value=response),
            mock.patch.object(target=uploader.api, attribute="request") as gh,
            mock.patch.object(target=system, attribute="program_path", return_value=self.program),
            mock.patch.object(target=sys, attribute="platform", new="linux"),
        ):
            store.install_app_update(update=update_with(asset=fields))

        job = store.app_update_job
        assert job is not None
        self.assertEqual(first=job.phase, second="done")
        self.assertEqual(first=self.program.read_bytes(), second=b"new program")
        gh.assert_not_called()

    def test_only_frozen_builds_with_an_asset_self_update(self) -> None:
        found = {"url": "x", "size": 1, "sha256": "a" * 64}
        self.assertFalse(expr=system.can_self_update(update=update_with(asset=found)))

        with (
            mock.patch.object(target=sys, attribute="frozen", new=True, create=True),
            mock.patch.object(target=system, attribute="program_path", return_value=self.program),
        ):
            self.assertTrue(expr=system.can_self_update(update=update_with(asset=found)))
            self.assertFalse(expr=system.can_self_update(update=update_with(asset=None)))
