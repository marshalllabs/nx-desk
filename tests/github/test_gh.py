import hashlib
import http.client
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Iterable, List, Optional
from unittest import mock

from nx_desk import uploader, zips
from nx_desk.schemas.common import Progress
from nx_desk.utils.callbacks import quiet
from tests.helpers import asset


class ApiRetryTests(unittest.TestCase):
    def run_request(self, method: str, errors: List[Exception]) -> mock.MagicMock:
        reply = mock.MagicMock()
        reply.read.return_value = b'"ok"'

        with (
            mock.patch.object(target=uploader.api, attribute="response") as response,
            mock.patch.object(target=uploader.api, attribute="check", side_effect=[*errors, None]) as check,
            mock.patch.object(target=time, attribute="sleep"),
        ):
            response.return_value.__enter__.return_value = reply
            self.assertEqual(first=uploader.api.request(path="synthetic", method=method), second="ok")

        return check

    def test_rate_limits_are_retried(self) -> None:
        limited = uploader.command.GitHubError("HTTP 403: rate limit", status=403)
        self.assertEqual(first=self.run_request(method="GET", errors=[limited]).call_count, second=2)

    def test_repeatable_server_errors_are_retried(self) -> None:
        broken = uploader.command.GitHubError("HTTP 502", status=502)

        for method in ("GET", "PATCH", "DELETE"):
            self.assertEqual(first=self.run_request(method=method, errors=[broken, broken]).call_count, second=3)

    def test_network_errors_retry_only_repeatable_requests(self) -> None:
        broken = uploader.command.NetworkError("interrupted")
        self.assertEqual(first=self.run_request(method="GET", errors=[broken]).call_count, second=2)

        with self.assertRaises(expected_exception=uploader.command.NetworkError):
            self.run_request(method="POST", errors=[broken])

    def test_creating_a_release_is_not_retried_after_server_error(self) -> None:
        broken = uploader.command.GitHubError("HTTP 502", status=502)

        with self.assertRaises(expected_exception=uploader.command.GitHubError):
            self.run_request(method="POST", errors=[broken])

    def test_rate_retries_are_bounded(self) -> None:
        limited = uploader.command.GitHubError("HTTP 429: rate limit", status=429)

        with self.assertRaises(expected_exception=uploader.command.GitHubError):
            self.run_request(method="GET", errors=[limited] * (len(uploader.command.RATE_WAITS) + 1))

    def test_other_errors_are_not_retried(self) -> None:
        with self.assertRaises(expected_exception=uploader.command.GitHubError):
            self.run_request(method="GET", errors=[uploader.command.GitHubError("HTTP 404", status=404)])

    def test_deleting_a_missing_file_succeeds(self) -> None:
        with mock.patch.object(
            target=uploader.api,
            attribute="request",
            side_effect=uploader.command.GitHubError("HTTP 404", status=404),
        ):
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

        def fake(repo: str, asset_id: int, target: Path, moved: Progress) -> None:
            error = next(errors, None)

            if error:
                (self.place / "a.zip").write_bytes(data=b"cut")
                raise uploader.command.GitHubError(error)

            (self.place / "a.zip").write_bytes(data=b"new")

        with (
            mock.patch.object(target=uploader.download, attribute="asset", new=fake),
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
        with self.assertRaises(expected_exception=uploader.command.GitHubError):
            self.fetch(failures=["connection reset by peer"] * (len(uploader.progress.NETWORK_WAITS) + 1))

    def test_other_errors_fail_at_once(self) -> None:
        with self.assertRaises(expected_exception=uploader.command.GitHubError):
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
        self.connection.getresponse.return_value = mock.MagicMock(status=status, read=lambda size=-1: body)

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

        with self.assertRaises(expected_exception=uploader.command.GitHubError) as caught:
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
