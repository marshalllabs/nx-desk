import http.client
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from typing import List
from unittest import mock

from nx_desk import uploader, zips
from nx_desk.schemas.api import ReleaseCreate


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = mock.MagicMock()
        self.reply = self.connection.getresponse.return_value
        self.reply.status = 200
        self.reply.read.return_value = b'{"login":"synthetic"}'
        self.reply.getheader.return_value = None
        patch = mock.patch.object(target=http.client, attribute="HTTPSConnection", return_value=self.connection)
        self.opened = patch.start()
        self.addCleanup(patch.stop)
        token = mock.patch.object(target=uploader.command, attribute="token", return_value="synthetic-pat")
        token.start()
        self.addCleanup(token.stop)

    def test_json_request_uses_api_headers_and_serializes_typed_payload(self) -> None:
        uploader.api.request(
            path="repos/example/mods/releases",
            method="POST",
            data=ReleaseCreate(tag_name="mods", name="mods"),
        )
        fields = self.connection.request.call_args.kwargs
        self.assertEqual(first=self.opened.call_args.kwargs["host"], second="api.github.com")
        self.assertEqual(first=fields["headers"]["Authorization"], second="Bearer synthetic-pat")
        self.assertEqual(first=fields["headers"]["Content-Type"], second="application/json")
        self.assertIn(member=b'"make_latest":"false"', container=fields["body"])
        self.connection.close.assert_called_once()

    def test_api_errors_never_echo_response_secrets(self) -> None:
        self.reply.status = 401
        self.reply.read.return_value = b'{"message":"synthetic-pat https://example.com/signed?token=private"}'

        with self.assertRaises(expected_exception=uploader.command.GitHubError) as caught:
            uploader.api.request(path="user")

        self.assertEqual(first=caught.exception.status, second=401)
        self.assertIn(member="Settings > GitHub", container=str(caught.exception))
        self.assertNotIn(member="synthetic-pat", container=str(caught.exception))
        self.assertNotIn(member="signed", container=str(caught.exception))

    def test_pagination_fetches_all_pages(self) -> None:
        with mock.patch.object(
            target=uploader.api,
            attribute="request",
            side_effect=[[None] * 100, ["last"]],
        ) as request:
            rows = uploader.api.pages(path="user/repos")

        self.assertEqual(first=len(rows), second=101)
        self.assertEqual(first=request.call_args_list[1].kwargs["path"], second="user/repos?per_page=100&page=2")

    def test_api_path_cannot_select_another_host(self) -> None:
        for path in ("https://example.com/path", "//example.com/path", "\\example.com", "user#fragment"):
            with self.subTest(path=path), self.assertRaises(expected_exception=ValueError):
                uploader.api.request(path=path)

        self.connection.request.assert_not_called()

    def test_invalid_json_is_a_github_error(self) -> None:
        self.reply.read.return_value = b"not json"

        with self.assertRaises(expected_exception=uploader.command.GitHubError):
            uploader.api.request(path="user")

    def test_stop_closes_the_connection(self) -> None:
        cancel = threading.Event()
        cancel.set()

        with uploader.command.stoppable(cancel=cancel), self.assertRaises(expected_exception=zips.Cancelled):
            uploader.api.request(path="user")

        self.connection.request.assert_not_called()
        self.connection.close.assert_called_once()

    def test_network_failure_does_not_echo_sensitive_exception_data(self) -> None:
        self.connection.request.side_effect = OSError("synthetic-pat")

        with (
            mock.patch.object(target=uploader.command, attribute="pause"),
            self.assertRaises(expected_exception=uploader.command.NetworkError) as caught,
        ):
            uploader.api.request(path="user")

        self.assertNotIn(member="synthetic-pat", container=str(caught.exception))

    def test_private_download_follows_redirect_without_forwarding_the_token(self) -> None:
        first, second = mock.MagicMock(), mock.MagicMock()
        first.getresponse.return_value.status = 302
        first.getresponse.return_value.getheader.return_value = "https://storage.example.com/asset?signature=synthetic"
        second.getresponse.return_value.status = 200
        second.getresponse.return_value.getheader.return_value = "3"
        second.getresponse.return_value.read.side_effect = [b"zip", b""]

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "mod.zip"
            self.opened.side_effect = [first, second]
            moved: List[int] = []
            uploader.download.asset(repo="example/mods", asset_id=7, target=target, moved=moved.append)
            self.assertEqual(first=target.read_bytes(), second=b"zip")

        self.assertIn(member="Authorization", container=first.request.call_args.kwargs["headers"])
        self.assertNotIn(member="Authorization", container=second.request.call_args.kwargs["headers"])
        self.assertEqual(first=moved, second=[0, 3])

    def test_download_refuses_plain_http_redirect(self) -> None:
        self.reply.status = 302
        self.reply.getheader.return_value = "http://storage.example.com/asset"

        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaises(expected_exception=uploader.command.GitHubError),
        ):
            uploader.download.asset(repo="example/mods", asset_id=7, target=Path(folder) / "mod.zip")

        self.assertEqual(first=self.opened.call_count, second=1)

    def test_truncated_download_is_retriable_network_error(self) -> None:
        self.reply.getheader.return_value = "20"
        self.reply.read.side_effect = [b"short", b""]

        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaises(expected_exception=uploader.command.NetworkError),
        ):
            uploader.download.asset(repo="example/mods", asset_id=7, target=Path(folder) / "mod.zip")


class BlockedRequestTests(unittest.TestCase):
    def test_cancel_interrupts_a_waiting_socket(self) -> None:
        reader, writer = socket.socketpair()
        connection = mock.Mock(sock=reader)
        cancel = threading.Event()
        reached = threading.Event()
        stopped = threading.Event()

        def blocked() -> None:
            with uploader.command.stoppable(cancel=cancel), uploader.command.interruptible(connection=connection):
                reached.set()
                reader.recv(1)
                stopped.set()

        thread = threading.Thread(target=blocked, daemon=True)

        try:
            thread.start()
            self.assertTrue(expr=reached.wait(timeout=2))
            cancel.set()
            self.assertTrue(expr=stopped.wait(timeout=2))
            thread.join(timeout=2)

        finally:
            reader.close()
            writer.close()
