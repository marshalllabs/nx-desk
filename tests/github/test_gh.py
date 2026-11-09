import hashlib
import http.client
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from unittest import mock

from nx_desk import uploader, zips
from nx_desk.utils.callbacks import quiet
from tests.helpers import asset


class RateLimitTests(unittest.TestCase):
    def test_gh_waits_and_tries_again_when_github_asks(self) -> None:
        limited = uploader.command.GhError("HTTP 403: You have exceeded a secondary rate limit")

        with (
            mock.patch.object(target=shutil, attribute="which", return_value="gh"),
            mock.patch.object(target=uploader.command, attribute="run_gh", side_effect=[limited, "ok"]) as run,
            mock.patch.object(target=time, attribute="sleep") as sleep,
        ):
            self.assertEqual(first=uploader.command.gh("api", "x"), second="ok")

        self.assertEqual(first=run.call_count, second=2)
        sleep.assert_called_once_with(uploader.command.RATE_WAITS[0])

    def test_other_errors_are_not_retried(self) -> None:
        with (
            mock.patch.object(target=shutil, attribute="which", return_value="gh"),
            mock.patch.object(
                target=uploader.command,
                attribute="run_gh",
                side_effect=uploader.command.GhError("HTTP 404"),
            ) as run,
            self.assertRaises(expected_exception=uploader.command.GhError),
        ):
            uploader.command.gh("api", "x")

        self.assertEqual(first=run.call_count, second=1)

    def test_it_gives_up_after_the_last_wait(self) -> None:
        limited = uploader.command.GhError("API rate limit exceeded")

        with (
            mock.patch.object(target=shutil, attribute="which", return_value="gh"),
            mock.patch.object(target=uploader.command, attribute="run_gh", side_effect=limited) as run,
            mock.patch.object(target=time, attribute="sleep"),
            self.assertRaises(expected_exception=uploader.command.GhError),
        ):
            uploader.command.gh("api", "x")

        self.assertEqual(first=run.call_count, second=len(uploader.command.RATE_WAITS) + 1)


class ServerErrorTests(unittest.TestCase):
    def run_gh(self, args: Tuple[str, ...], failures: int) -> mock.MagicMock:
        broken = uploader.command.GhError("gh: Server Error (HTTP 502)")

        with (
            mock.patch.object(target=shutil, attribute="which", return_value="gh"),
            mock.patch.object(
                target=uploader.command,
                attribute="run_gh",
                side_effect=[broken] * failures + ["ok"],
            ) as run,
            mock.patch.object(target=time, attribute="sleep"),
        ):
            uploader.command.gh(*args)

        return run

    def test_a_repeatable_call_is_sent_again(self) -> None:
        for args in (("api", "repos/me/mods/releases"), ("api", "-X", "PATCH", "x"), ("api", "-X", "DELETE", "x")):
            self.assertEqual(first=self.run_gh(args=args, failures=2).call_count, second=3)

    def test_a_call_that_creates_something_is_not_sent_again(self) -> None:
        for args in (("release", "create", "tag"), ("api", "-X", "POST", "x")):
            with self.assertRaises(expected_exception=uploader.command.GhError):
                self.run_gh(args=args, failures=1)

    def test_it_gives_up_after_the_last_wait(self) -> None:
        with self.assertRaises(expected_exception=uploader.command.GhError):
            self.run_gh(args=("api", "x"), failures=len(uploader.command.SERVER_WAITS) + 1)

    def test_deleting_a_file_already_gone_succeeds(self) -> None:
        gone = uploader.command.GhError("HTTP 404: Not Found")

        with mock.patch.object(target=uploader.command, attribute="gh", side_effect=gone):
            uploader.releases.delete_asset(repo="me/mods", asset=asset(name="a.zip"))


class TransferRetryTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.place = Path(folder.name)
        self.lines: List[str] = []
        self.assets = {
            "a.zip": asset(name="a.zip", size=3, digest=f"sha256:{hashlib.sha256(string=b'new').hexdigest()}"),
        }

    def fetch(self, failures: Iterable[Optional[str]]) -> mock.MagicMock:
        errors = iter(failures)

        def fake(*args: str) -> str:
            error = next(errors, None)

            if error:
                (self.place / "a.zip").write_bytes(data=b"cut")
                raise uploader.command.GhError(error)

            (self.place / "a.zip").write_bytes(data=b"new")

            return ""

        with (
            mock.patch.object(target=uploader.command, attribute="gh", new=fake),
            mock.patch.object(target=time, attribute="sleep") as sleep,
        ):
            uploader.parts.download_group(
                repo="me/mods",
                tag="tag",
                names=["a.zip"],
                assets=self.assets,
                place=self.place,
                report=self.lines.append,
            )

        return sleep

    def test_a_lost_connection_is_tried_again_from_the_start(self) -> None:
        sleep = self.fetch(failures=["read tcp 1.2.3.4:5->6.7.8.9:443: read: connection reset by peer"])
        sleep.assert_called_once_with(uploader.progress.NETWORK_WAITS[0])
        self.assertEqual(first=(self.place / "a.zip").read_bytes(), second=b"new")
        self.assertTrue(expr=any("trying again" in line for line in self.lines))

    def test_it_gives_up_after_the_last_wait(self) -> None:
        with self.assertRaises(expected_exception=uploader.command.GhError):
            self.fetch(failures=["connection reset by peer"] * (len(uploader.progress.NETWORK_WAITS) + 1))

    def test_other_errors_fail_at_once(self) -> None:
        with self.assertRaises(expected_exception=uploader.command.GhError):
            self.fetch(failures=["HTTP 404: Not Found"])

        self.assertFalse(expr=any("trying again" in line for line in self.lines))


class PostAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "a b.zip"
        self.path.write_bytes(data=b"x" * (uploader.upload.UPLOAD_BLOCK + 10))
        self.connection = mock.MagicMock()
        patcher = mock.patch.object(
            target=http.client,
            attribute="HTTPSConnection",
            return_value=self.connection,
        )
        self.opened = patcher.start()
        self.addCleanup(patcher.stop)

    def respond(self, status: int, body: bytes = b"{}") -> None:
        self.connection.getresponse.return_value = mock.MagicMock(status=status, read=lambda: body)

    def test_sends_the_file_in_counted_pieces_to_the_upload_host_only(self) -> None:
        self.respond(status=201)
        moved: List[int] = []
        uploader.upload.post_asset(repo="me/mods", release=7, path=self.path, token="secret", moved=moved.append)
        self.assertEqual(first=self.opened.call_args.kwargs["host"], second="uploads.github.com")
        self.assertEqual(first=moved, second=[uploader.upload.UPLOAD_BLOCK, uploader.upload.UPLOAD_BLOCK + 10])
        request = self.connection.putrequest.call_args.kwargs
        self.assertEqual(
            first=request,
            second={"method": "POST", "url": "/repos/me/mods/releases/7/assets?name=a+b.zip"},
        )
        headers = dict(call[0] for call in self.connection.putheader.call_args_list)
        self.assertEqual(first=headers["Authorization"], second="Bearer secret")
        self.assertEqual(first=headers["Content-Length"], second=str(uploader.upload.UPLOAD_BLOCK + 10))

    def test_a_refusal_reports_githubs_message_and_never_the_token(self) -> None:
        self.respond(status=403, body=b'{"message": "You have exceeded a secondary rate limit"}')

        with self.assertRaises(expected_exception=uploader.command.GhError) as caught:
            uploader.upload.post_asset(repo="me/mods", release=7, path=self.path, token="secret", moved=quiet)

        self.assertIn(member="rate limit", container=str(caught.exception))
        self.assertNotIn(member="secret", container=str(caught.exception))

    def test_a_lost_connection_counts_as_network_trouble(self) -> None:
        self.connection.send.side_effect = ConnectionResetError("reset")

        with self.assertRaises(expected_exception=uploader.command.NetworkError):
            uploader.upload.post_asset(repo="me/mods", release=7, path=self.path, token="secret", moved=quiet)

    def test_stop_ends_the_upload(self) -> None:
        cancel = threading.Event()
        cancel.set()

        with uploader.command.stoppable(cancel=cancel), self.assertRaises(expected_exception=zips.Cancelled):
            uploader.upload.post_asset(repo="me/mods", release=7, path=self.path, token="secret", moved=quiet)

        self.connection.close.assert_called()
