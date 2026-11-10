import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest import mock

from nx_desk import uploader, vault
from tests.helpers import FakeGitHub


class GitHubCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        self.src = self.base / "src"
        self.store = vault.Vault(base=self.base / "data")
        self.hub = FakeGitHub()

        for patcher in (
            mock.patch.object(target=uploader.api, attribute="request", new=self.hub.request),
            mock.patch.object(target=uploader.api, attribute="pages", new=self.hub.pages),
            mock.patch.object(target=uploader.download, attribute="asset", new=self.hub.download),
            mock.patch.object(target=uploader.command, attribute="token", return_value="token"),
            mock.patch.object(target=uploader.upload, attribute="post_asset", new=self.hub.post),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.mod(name="Stardew Valley - [VI] - [1.0]", data=b"stardew", extra={"backup/old.zip": b"old"})
        self.mod(name="Hades - [VI] - [1.0]", data=b"h")
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="reviewed")

    # A valid mod folder holds a zip of the same name.
    def mod(
        self,
        name: str,
        data: bytes = b"zip",
        extra: Optional[Dict[str, bytes]] = None,
        root: Optional[Path] = None,
    ) -> Path:
        base = (root or self.src) / name
        base.mkdir(parents=True, exist_ok=True)
        (base / f"{name}.zip").write_bytes(data=data)

        for rel, payload in (extra or {}).items():
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data=payload)

        return base

    def put(self, relative: str, data: bytes) -> None:
        path = self.src / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data=data)

    def statuses(self) -> Dict[str, str]:
        return {folder.name: folder.status for folder in self.store.upload_job.folders}

    def reupload_then_remove(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Stardew Valley - [VI] - [1.0]", "Hades - [VI] - [1.0]"])
        shutil.rmtree(path=self.src / "Stardew Valley - [VI] - [1.0]")

    def fresh_source(self) -> Path:
        src = self.base / "fresh"
        src.mkdir()
        self.store.set_upload_settings(source=str(src), repo="me/mods", tag="reviewed")

        return src
