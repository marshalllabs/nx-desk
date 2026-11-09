import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from typing import Dict
from unittest import mock

from nx_desk import net, uploader, vault
from nx_desk.schemas.catalog import Catalog, Mod
from nx_desk.schemas.download import Fetched
from nx_desk.schemas.state import ReleaseRecord
from nx_desk.utils.json import parse_json
from tests.helpers import TITLE, FakeGitHub, mod


class AutoUploadCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.store = vault.Vault(base=self.base / "data")
        self.store.set_mod_name(name="VI")
        self.store.set_download_dir(text=str(self.base / "downloads"))
        self.store.catalogs = [Catalog(name="My Catalog", url="https://x.test/c.json", folder="my-catalog")]
        self.store.select_catalog(folder="my-catalog")
        self.store.set_upload_settings(source="", repo="me/mods", tag="")
        self.store.set_auto_repo(repo="me/mods")
        self.store.set_auto_upload(enabled=True)
        self.hub = FakeGitHub()
        self.hub.releases = ["reviewed"]

        for patcher in (
            mock.patch.object(target=uploader.command, attribute="gh", new=self.hub),
            mock.patch.object(target=uploader.upload, attribute="post_asset", new=self.hub.post),
            mock.patch.object(target=net, attribute="http_get"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def download(self, item: Mod) -> None:
        source = self.base / f"{item.id}.zip"

        with zipfile.ZipFile(file=source, mode="w") as output:
            output.writestr(zinfo_or_arcname=f"{TITLE}/romfs/a.bin", data=item.id)

        self.store.items = [item]
        self.store.enqueue(ids=[item.id])
        task = self.store.queue.get()
        queued, cancel = task.entry, task.cancel

        with mock.patch.object(target=self.store, attribute="_download", return_value=Fetched(wire=source)):
            self.store._run_download(entry=queued, cancel=cancel)
            self.store._repack_next()

        deadline = time.monotonic() + 5

        while self.store.auto_uploading() and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertFalse(expr=self.store.auto_uploading())

    def remote_state(self) -> Dict[str, ReleaseRecord]:
        return uploader.state.clean_state(data=parse_json(text=self.hub.blobs["state.json"]))

    def item(self, sha: str = "a", version: str = "1.0") -> Mod:
        return mod(name="Game", sha256=sha * 64, game_version=version)

    def github_tab(self) -> None:
        self.store.set_upload_settings(source=str(self.store.root), repo="me/mods", tag="my-catalog")
        self.store.set_auto_repo(repo="me/mods")
        self.store.scan_upload()

    def run_until_saved(self, item: Mod) -> None:
        source = self.base / f"{item.id}.zip"

        with zipfile.ZipFile(file=source, mode="w") as output:
            output.writestr(zinfo_or_arcname=f"{TITLE}/romfs/a.bin", data=item.id)

        self.store.items = [item]
        self.store.enqueue(ids=[item.id])
        task = self.store.queue.get()
        queued, cancel = task.entry, task.cancel

        with mock.patch.object(target=self.store, attribute="_download", return_value=Fetched(wire=source)):
            self.store._run_download(entry=queued, cancel=cancel)
            self.store._repack_next()

    def wait_for_uploads(self) -> None:
        deadline = time.monotonic() + 5

        while self.store.auto_uploading() and time.monotonic() < deadline:
            time.sleep(0.01)

        self.assertFalse(expr=self.store.auto_uploading())
