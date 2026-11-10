import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Set
from urllib.parse import unquote

from pydantic import BaseModel, JsonValue

from nx_desk import uploader
from nx_desk.catalog.parse import normalize
from nx_desk.schemas.catalog import Mod
from nx_desk.schemas.common import Progress
from nx_desk.schemas.download import Job
from nx_desk.schemas.github import Asset
from nx_desk.schemas.snapshot import ModRow
from nx_desk.utils.json import parse_json

sys.dont_write_bytecode = True


TITLE = "0100BA4026E94000"


def entry(**overrides: object) -> Dict[str, object]:
    fields = {
        "id": "game",
        "sha256": "0" * 64,
        "size": 1,
        "url": "https://example.com/a.zip",
        "name": "Game",
        "title_id": TITLE,
    }

    return {**fields, **overrides}


def normal(raw: object) -> Mod:
    item = normalize(raw=raw)
    assert item is not None

    return item


def mod(**overrides: object) -> Mod:
    return normal(raw=entry(**overrides))


# Tests set only the fields they check; the rest keep these defaults.
def row(**overrides: object) -> ModRow:
    fields = {**mod().model_dump(), "status": "missing", "remote": False, "local_version": "", "local_game_version": ""}

    return ModRow.model_validate(obj={**fields, "job": None, **overrides})


def asset(name: str, **overrides: object) -> Asset:
    fields = {"id": 1, "name": name, "size": 0, "digest": None, "label": None, "updated_at": ""}

    return Asset.model_validate(obj={**fields, **overrides})


def job(**overrides: object) -> Job:
    fields = {"phase": "queued", "done": 0, "total": 0, "speed": 0, "game": "Game", "weight": 0}

    return Job.model_validate(obj={**fields, **overrides})


class FakeGitHub:
    def __init__(self) -> None:
        # Release files as the GitHub API would return them.
        self.assets: Dict[str, Asset] = {}
        self.blobs: Dict[str, bytes] = {}

        self.releases = ["reviewed"]
        # Git tags of the repository: a release takes one, and renaming a release leaves the old one behind.
        self.tags: Set[str] = {"reviewed"}
        self.keep_tags = False
        self.repos = ["me/zeta", "Me/alpha"]
        self.latest = "reviewed"
        self.next_id = 1
        self.logged_in = True

    def request(self, path: str, method: str = "GET", data: Optional[BaseModel] = None) -> JsonValue:
        if path == "user":
            if not self.logged_in:
                raise uploader.command.GitHubError("HTTP 401: Replace the token in Settings > GitHub.", status=401)

            return {"login": "synthetic"}

        if path.startswith("user/repos"):
            return parse_json(
                text=json.dumps(
                    obj=[
                        {
                            "full_name": name,
                            "name": name.split(sep="/")[1],
                            "owner": {"login": name.split(sep="/")[0]},
                            "visibility": "public",
                        }
                        for name in self.repos
                    ],
                ),
            )

        if "/git/refs/tags/" in path:
            self.delete_tag(tag=unquote(string=path.split(sep="/git/refs/tags/")[1]))

            return None

        if path.endswith("/releases/latest"):
            if not self.latest:
                raise uploader.command.GitHubError("HTTP 404", status=404)

            return {"tag_name": self.latest}

        if "/releases/tags/" in path:
            tag = unquote(string=path.split(sep="/releases/tags/")[1])

            return {"id": self.releases.index(tag) + 1 if tag in self.releases else 1, "tag_name": tag}

        if "/releases/assets/" in path:
            number = int(path.rsplit("/", 1)[1])
            item = next(asset for asset in self.assets.values() if asset.id == number)
            del self.assets[item.name]

            if method == "PATCH":
                assert data is not None
                old = item.name
                item = item.model_copy(update=data.model_dump(exclude_none=True))
                self.assets[item.name] = item
                self.blobs[item.name] = self.blobs.pop(old, b"")

            return None

        if path.endswith("/releases"):
            if method == "POST":
                assert data is not None
                tag = str(data.model_dump()["tag_name"])
                self.releases.append(tag)
                self.tags.add(tag)

                return {"id": len(self.releases), "tag_name": tag}

            return [{"tag_name": tag} for tag in self.releases]

        if path.endswith("/assets"):
            return parse_json(text=json.dumps(obj=[asset.model_dump(mode="json") for asset in self.assets.values()]))

        if "/releases/" in path:
            number = int(path.rsplit("/", 1)[1])
            old = self.releases[number - 1]

            if method == "PATCH":
                assert data is not None
                new = str(data.model_dump()["tag_name"])
                self.releases[number - 1] = new
                self.tags.add(new)

                if self.latest == old:
                    self.latest = new

            elif method == "DELETE":
                self.releases.remove(old)
                self.assets = {}

                if self.latest == old:
                    self.latest = self.releases[0] if self.releases else ""

            return None

        raise AssertionError(f"Unexpected API request: {method} {path}")

    def pages(self, path: str) -> JsonValue:
        return self.request(path=path)

    def download(self, repo: str, asset_id: int, target: Path, moved: Progress = lambda done: None) -> None:
        item = next(asset for asset in self.assets.values() if asset.id == asset_id)
        target.write_bytes(data=self.blobs[item.name])
        moved(target.stat().st_size)

    def post(self, repo: str, release: int, path: Path, token: str, moved: Progress) -> None:
        assert token == "token"
        moved(path.stat().st_size)
        self.add(name=path.name, digest=f"sha256:{hashlib.sha256(string=path.read_bytes()).hexdigest()}")
        self.assets[path.name].size = path.stat().st_size
        self.assets[path.name].updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 1))
        self.blobs[path.name] = path.read_bytes()

    def add(self, name: str, digest: str) -> None:
        self.assets[name] = Asset(id=self.next_id, name=name, digest=digest)
        self.next_id += 1

    def delete_tag(self, tag: str) -> str:
        if self.keep_tags:
            raise uploader.command.GitHubError("HTTP 403: Resource not accessible", status=403)

        if tag not in self.tags:
            raise uploader.command.GitHubError("HTTP 422: Reference does not exist", status=422)

        self.tags.discard(tag)

        return ""
