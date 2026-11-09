import hashlib
import http.client
import re
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from .. import config as settings
from .. import net, system
from ..config import ASSET_DIGEST, CHUNK, MAX_UPDATE, VERSION_KEY
from ..schemas.api import ReleasePayload
from ..schemas.update import AppAsset, AppUpdate, UpdateJob
from ..system import asset_name, extract_program, swap_program
from ..utils.urls import https_or_empty
from .base import VaultBase


def parse_version(text: object) -> Optional[Tuple[int, ...]]:
    match = re.fullmatch(pattern=r"v?(\d+)\.(\d+)\.(\d+)", string=str(text).strip())

    return tuple(int(part) for part in match.groups()) if match else None


class AppUpdates(VaultBase):
    def check_app_update(self) -> str:
        config = settings.load_config()
        current = parse_version(text=config.get(VERSION_KEY, ""))
        url = config.get("NX_DESK_RELEASES_URL")

        if current is None or not url:
            return "unversioned"

        try:
            release = self._latest_release(url=url)
            latest = parse_version(text=release.tag_name)
            page = https_or_empty(value=release.html_url)

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            http.client.HTTPException,
        ):
            return "error"

        if latest is None:
            return "error"

        if latest <= current:
            return "current"

        if not page:
            return "error"

        with self.lock:
            self.app_update = AppUpdate(tag=release.tag_name, url=page, asset=self.pick_asset(release=release))

        return "available"

    @staticmethod
    def _latest_release(url: str) -> ReleasePayload:
        with net.http_get(url=url, headers={"Accept": "application/vnd.github+json"}) as response:
            return ReleasePayload.model_validate_json(json_data=response.read())

    @staticmethod
    def pick_asset(release: ReleasePayload) -> Optional[AppAsset]:
        for asset in release.assets:
            if asset.name == asset_name():
                url = asset.browser_download_url
                size = asset.size
                digest = asset.digest

                if (
                    isinstance(url, str)
                    and url.startswith("https://github.com/")
                    and isinstance(size, int)
                    and 0 < size <= MAX_UPDATE
                    and isinstance(digest, str)
                    and ASSET_DIGEST.match(string=digest)
                ):
                    return AppAsset(url=url, size=size, sha256=digest[len("sha256:") :])

                return None

        return None

    def set_update_job(self, **fields: object) -> None:
        with self.lock:
            job = self.app_update_job or UpdateJob()
            self.app_update_job = job.model_copy(update=fields)

    def download_update(self, asset: AppAsset, path: Path) -> None:
        self._stream_download(asset=asset, path=path)
        self._verify_file(path=path, asset=asset)

    def _stream_download(self, asset: AppAsset, path: Path) -> None:
        done = 0

        with net.http_get(url=asset.url) as response, open(file=path, mode="wb") as handle:
            for block in iter(lambda: response.read(CHUNK), b""):
                done += len(block)

                if done > asset.size:
                    raise RuntimeError("file is larger than the size in the release")

                handle.write(block)
                self.set_update_job(done=done)

    @staticmethod
    def _verify_file(path: Path, asset: AppAsset) -> None:
        digest = hashlib.sha256()
        size = 0

        with open(file=path, mode="rb") as handle:
            for block in iter(lambda: handle.read(CHUNK), b""):
                size += len(block)
                digest.update(block)

        if size != asset.size or digest.hexdigest() != asset.sha256:
            raise RuntimeError("the update does not match the release SHA-256")

    def install_app_update(self, update: AppUpdate) -> None:
        asset = update.asset

        if asset is None:
            self.set_update_job(phase="error", message="the release has no file for this system")

            return

        program = system.program_path()
        work = self.parts / "app-update"
        self.set_update_job(phase="downloading", done=0, total=asset.size, message="")

        try:
            shutil.rmtree(path=work, ignore_errors=True)
            work.mkdir(parents=True)
            archive = work / asset_name()
            self.download_update(asset=asset, path=archive)
            self.set_update_job(phase="installing")
            swap_program(
                new=extract_program(archive=archive, target=work / "extracted", name=program.name),
                program=program,
            )
            self.set_update_job(phase="done")

        except (
            OSError,
            ValueError,
            RuntimeError,
            zipfile.BadZipFile,
            subprocess.SubprocessError,
            http.client.HTTPException,
        ) as error:
            self.set_update_job(phase="error", message=str(error) or type(error).__name__)

        finally:
            shutil.rmtree(path=work, ignore_errors=True)
