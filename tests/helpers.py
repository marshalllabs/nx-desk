import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from nx_desk import uploader
from nx_desk.catalog.parse import normalize
from nx_desk.schemas.catalog import Mod
from nx_desk.schemas.common import Progress
from nx_desk.schemas.download import Job
from nx_desk.schemas.github import Asset
from nx_desk.schemas.snapshot import ModRow

sys.dont_write_bytecode = True


TITLE = "0100BA4026E94000"


def entry(**overrides: object) -> dict[str, object]:
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
    fields = {**dict(mod()), "status": "missing", "remote": False, "local_version": "", "local_game_version": ""}

    return ModRow.model_validate({**fields, "job": None, **overrides})


def asset(name: str, **overrides: object) -> Asset:
    fields = {"id": 1, "name": name, "size": 0, "digest": None, "label": None, "updated_at": ""}

    return Asset.model_validate({**fields, **overrides})


def job(**overrides: object) -> Job:
    fields = {"phase": "queued", "done": 0, "total": 0, "speed": 0, "game": "Game", "weight": 0}

    return Job.model_validate({**fields, **overrides})


class FakeGitHub:
    def __init__(self) -> None:
        # Release files as the GitHub API would return them.
        self.assets: dict[str, dict[str, Any]] = {}
        self.blobs: dict[str, bytes] = {}

        self.releases = ["reviewed"]
        # Git tags of the repository: a release takes one, and renaming a release leaves the old one behind.
        self.tags: set[str] = {"reviewed"}
        self.keep_tags = False
        self.repos = ["me/zeta", "Me/alpha"]
        self.latest = "reviewed"
        self.next_id = 1
        self.logged_in = True

    def __call__(self, *args: str) -> str:
        if args[:2] == ("auth", "status"):
            if not self.logged_in:
                raise uploader.command.GhError("not logged in")

            return ""

        if args[:2] == ("auth", "token"):
            return "token\n"

        if args[-1].startswith("user/repos"):
            rows = [
                {
                    "full_name": name,
                    "name": name.split("/")[1],
                    "owner": {"login": name.split("/")[0]},
                    "visibility": "public",
                }
                for name in self.repos
            ]

            return json.dumps(obj=[rows])

        if args[-1].endswith("/releases/latest"):
            if not self.latest:
                raise uploader.command.GhError("HTTP 404")

            return json.dumps(obj={"tag_name": self.latest})

        if args[:2] == ("release", "create"):
            self.releases.append(args[2])
            self.tags.add(args[2])

            return ""

        if args[:2] == ("release", "edit"):
            new = args[args.index("--tag") + 1]
            self.releases = [new if tag == args[2] else tag for tag in self.releases]
            self.tags.add(new)

            if self.latest == args[2]:
                self.latest = new

            return ""

        if args[:2] == ("release", "delete"):
            self.releases = [tag for tag in self.releases if tag != args[2]]
            self.assets = {}

            if "--cleanup-tag" in args:
                self.tags.discard(args[2])

            if self.latest == args[2]:
                self.latest = self.releases[0] if self.releases else ""

            return ""

        if args[:2] == ("release", "upload"):
            path = Path(args[3])
            self.add(name=path.name, digest=f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}")
            self.assets[path.name]["size"] = path.stat().st_size
            self.assets[path.name]["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 1))
            self.blobs[path.name] = path.read_bytes()

            return ""

        if args[:2] == ("release", "download"):
            name = args[args.index("--pattern") + 1]
            (Path(args[args.index("--dir") + 1]) / name).write_bytes(data=self.blobs[name])

            return ""

        if "-X" in args and "/git/refs/tags/" in args[-1]:
            return self.delete_tag(tag=args[-1].rsplit("/", 1)[1])

        if "-X" in args:
            return self.change(args=args)

        url = args[-1]

        if url.endswith("/releases?per_page=100"):
            return json.dumps(obj=[[{"tag_name": tag} for tag in self.releases]])

        if "/releases/tags/" in url:
            return json.dumps(obj={"id": 1})

        return json.dumps(obj=[list(self.assets.values())])

    def post(self, repo: str, release: int, path: Path, token: str, moved: Progress) -> None:
        assert token == "token"
        moved(path.stat().st_size)
        self("release", "upload", "tag", str(path))

    def add(self, name: str, digest: str) -> None:
        self.assets[name] = {"id": self.next_id, "name": name, "digest": digest}
        self.next_id += 1

    def delete_tag(self, tag: str) -> str:
        if self.keep_tags:
            raise uploader.command.GhError("HTTP 403: Resource not accessible")

        if tag not in self.tags:
            raise uploader.command.GhError("HTTP 422: Reference does not exist")

        self.tags.discard(tag)

        return ""

    def change(self, args: tuple[str, ...]) -> str:
        number = int(args[3].rsplit("/", 1)[1])
        asset = next(item for item in self.assets.values() if item["id"] == number)
        del self.assets[asset["name"]]

        if args[2] == "PATCH":
            old = asset["name"]
            fields = dict(args[index + 1].split("=", 1) for index, arg in enumerate(args) if arg == "-f")
            asset.update(fields)
            self.assets[asset["name"]] = asset
            self.blobs[asset["name"]] = self.blobs.pop(old, b"")

        return ""
