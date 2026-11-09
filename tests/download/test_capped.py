import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Callable, Dict, Optional
from unittest import mock

from nx_desk import net, vault
from tests.helpers import job, mod


class CappedServer:
    def __init__(self, data: bytes, cap: int) -> None:
        self.data = data
        self.cap = cap
        self.calls = 0

    def __call__(self, url: str, headers: Optional[Dict[str, str]] = None) -> mock.MagicMock:
        self.calls += 1
        start = int(headers["Range"][6:].split(sep="-")[0]) if headers else 0
        piece = self.data[start : start + self.cap]
        response = mock.MagicMock()
        response.status = 206
        response.headers = {"Content-Range": f"bytes {start}-{start + len(piece) - 1}/{len(self.data)}"}
        reader = io.BytesIO(initial_bytes=piece)
        response.__enter__.return_value = response
        response.read = reader.read

        return response


class CappedDownloadTests(unittest.TestCase):
    def fetch(self, server: Callable[..., object], size: int) -> bytes:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            item = mod(id="game", name="Game", size=size)
            store.jobs["game"] = job(phase="downloading", total=size)
            part = Path(folder) / "game.part"

            with mock.patch.object(target=net, attribute="http_get", new=server):
                store._fetch(entry=item, url="https://x.test/a.zip", part=part, cancel=threading.Event())

            return part.read_bytes()

    def test_keeps_asking_when_a_server_caps_each_reply(self) -> None:
        data = os.urandom(5000)
        server = CappedServer(data=data, cap=2000)
        self.assertEqual(first=self.fetch(server=server, size=5000), second=data)
        self.assertEqual(first=server.calls, second=3)

    def test_works_when_the_catalog_gives_no_size(self) -> None:
        data = os.urandom(5000)
        self.assertEqual(first=self.fetch(server=CappedServer(data=data, cap=2000), size=0), second=data)

    def test_a_server_that_stops_sending_is_still_an_error(self) -> None:
        server = CappedServer(data=os.urandom(100), cap=100)

        with self.assertRaises(expected_exception=OSError):
            self.fetch(server=server, size=5000)

    def test_a_cut_reply_without_range_support_is_still_an_error(self) -> None:
        def plain(url: str, headers: Optional[Dict[str, str]] = None) -> mock.MagicMock:
            response = mock.MagicMock()
            response.status = 200
            response.headers = {}
            response.read = io.BytesIO(initial_bytes=b"x" * 10).read
            response.__enter__.return_value = response

            return response

        with self.assertRaises(expected_exception=OSError):
            self.fetch(server=plain, size=5000)
