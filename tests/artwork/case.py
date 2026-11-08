import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from email.message import Message
from pathlib import Path
from typing import Any
from unittest import mock

from nx_desk import credentials
from nx_desk.vault import Vault

GRID = "https://cdn.test/grid/cover.png"
HERO = "https://cdn.test/hero/background.jpg"


class Response:
    def __init__(self, body: bytes) -> None:
        self.body = io.BytesIO(body)

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def read(self, size: int = -1) -> bytes:
        return self.body.read(size)


def http_error(url: str, code: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    message = Message()

    for name, value in (headers or {}).items():
        message[name] = value

    return urllib.error.HTTPError(url=url, code=code, msg="error", hdrs=message, fp=io.BytesIO(b"{}"))


def reply(data: object) -> Response:
    return Response(body=json.dumps(obj={"success": True, "data": data}).encode("utf-8"))


# Answers like SteamGridDB: one known game, its grid only at 600x900, and its hero.
class FakeSteamGridDB:
    def __init__(self, games: dict[str, int] | None = None, refuse: int = 0) -> None:
        self.games = {"Game": 7} if games is None else games
        self.refuse = refuse
        self.calls: list[str] = []
        self.keys: list[str] = []
        self.images: list[str] = []

    def __call__(self, url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Response:
        if not url.startswith("https://www.steamgriddb.com/"):
            self.images.append(url)

            return Response(body=b"image")

        self.calls.append(url)
        self.keys.append((headers or {}).get("Authorization", ""))

        if self.refuse:
            raise http_error(url=url, code=self.refuse, headers={"Retry-After": "120"})

        parts = urllib.parse.urlsplit(url)
        path = urllib.parse.unquote(parts.path.removeprefix("/api/v2"))
        query = urllib.parse.parse_qs(parts.query)

        if path.startswith("/search/autocomplete/"):
            name = path.removeprefix("/search/autocomplete/")
            found = [{"id": game_id, "name": name} for title, game_id in self.games.items() if title == name]

            return reply(data=found)

        if path == "/grids/game/7":
            return reply(data=[{"url": GRID}] if query.get("dimensions") == ["600x900"] else [])

        if path == "/heroes/game/7":
            return reply(data=[{"url": HERO}])

        raise http_error(url=url, code=404)


class ArtCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        # Tests never reach the real system keyring.
        self.keyring: dict[str, str] = {}
        patcher = mock.patch.object(credentials, "keyring", self.fake_keyring())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.vault = Vault(base=self.folder)

    def fake_keyring(self) -> Any:
        fake = mock.Mock()
        fake.set_password.side_effect = lambda service, user, value: self.keyring.__setitem__(user, value)
        fake.get_password.side_effect = lambda service, user: self.keyring.get(user)
        fake.delete_password.side_effect = lambda service, user: self.keyring.pop(user, None)

        return fake

    def break_keyring(self) -> None:
        credentials.keyring.set_password.side_effect = RuntimeError("no keyring")  # type: ignore[attr-defined]
