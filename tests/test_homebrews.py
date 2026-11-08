import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nx_desk import config, net
from nx_desk.catalog.homebrews import find_homebrews, parse_homebrews
from nx_desk.config import HOMEBREWS_FILE, HOMEBREWS_KEY
from nx_desk.vault import Vault

DATA = {
    "homebrews": [
        {
            "id": "tool",
            "name": "Example Tool",
            "description": "Manage local files",
            "groups": ["Applications", "Plugins"],
            "category": "Utilities",
            "version": "2.0",
            "authors": "Example Author",
            "updated": "2026-10-12",
            "url": "https://example.com/wiki/Tool",
        },
    ],
}


class HomebrewParsingTests(unittest.TestCase):
    def test_parses_metadata(self) -> None:
        rows = parse_homebrews(data=DATA)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].groups, ["Applications", "Plugins"])
        self.assertEqual(rows[0].description, "Manage local files")
        self.assertEqual(rows[0].authors, "Example Author")

    def test_drops_invalid_entries_and_duplicate_ids(self) -> None:
        row = DATA["homebrews"][0]
        data = {"homebrews": [None, {}, {"id": "no-name"}, row, row]}
        self.assertEqual(len(parse_homebrews(data=data)), 1)

    def test_sanitizes_links_and_groups(self) -> None:
        row = {**DATA["homebrews"][0], "url": "javascript:alert(1)", "groups": [None, 1, "Games", " Games "]}
        result = parse_homebrews(data={"homebrews": [row]})[0]
        self.assertEqual(result.url, "")
        self.assertEqual(result.groups, ["Games"])

    def test_search_matches_all_words_across_fields(self) -> None:
        rows = parse_homebrews(data=DATA)
        self.assertEqual(find_homebrews(rows=rows, query="files author plugins"), rows)
        self.assertEqual(find_homebrews(rows=rows, query="files missing"), [])
        self.assertEqual(find_homebrews(rows=rows, query=" "), rows)

    def test_invalid_document_shapes_are_empty(self) -> None:
        shapes: tuple[object, ...] = (None, [], {}, {"homebrews": "invalid"})

        for shape in shapes:
            self.assertEqual(parse_homebrews(data=shape), [])


class HomebrewCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="homebrew-cache-")
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.store = Vault(base=self.base)
        self.path = self.store.cache_dir / HOMEBREWS_FILE
        self.raw = json.dumps(obj=DATA).encode()
        settings = mock.patch.object(
            config,
            "load_config",
            return_value={HOMEBREWS_KEY: "https://example.com/feed.json"},
        )
        settings.start()
        self.addCleanup(settings.stop)

    def response(self, raw: bytes) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = raw

        return response

    def test_fetches_valid_data_and_reuses_fresh_cache(self) -> None:
        with mock.patch.object(net, "http_get", return_value=self.response(raw=self.raw)) as fetch:
            self.store.load_homebrews()
            self.store.load_homebrews()

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(self.path.read_bytes(), self.raw)
        self.assertEqual(len(self.store.homebrew_snapshot().rows), 1)
        self.assertFalse(self.store.homebrew_snapshot().loading)
        self.assertEqual(self.store.homebrew_snapshot().error, "")

    def test_failed_refresh_keeps_cached_rows_and_file(self) -> None:
        self.path.write_bytes(data=self.raw)

        with mock.patch.object(net, "http_get", side_effect=OSError("offline")):
            self.store.load_homebrews(force=True)

        snapshot = self.store.homebrew_snapshot()
        self.assertEqual(len(snapshot.rows), 1)
        self.assertEqual(snapshot.error, "offline")
        self.assertFalse(snapshot.loading)
        self.assertEqual(self.path.read_bytes(), self.raw)

    def test_empty_and_invalid_responses_do_not_replace_cache(self) -> None:
        self.path.write_bytes(data=self.raw)

        for raw in (b'{"homebrews": []}', b"not JSON"):
            with mock.patch.object(net, "http_get", return_value=self.response(raw=raw)):
                self.store.load_homebrews(force=True)

            self.assertEqual(self.path.read_bytes(), self.raw)
            self.assertTrue(self.store.homebrew_snapshot().error)

    def test_oversized_response_is_rejected(self) -> None:
        with (
            mock.patch("nx_desk.vault.homebrews.MAX_CATALOG", 10),
            mock.patch.object(
                net,
                "http_get",
                return_value=self.response(raw=b"x" * 11),
            ),
        ):
            self.store.load_homebrews(force=True)

        self.assertIn("too large", self.store.homebrew_snapshot().error)
        self.assertFalse(self.path.exists())

    def test_missing_feed_reports_configuration_error(self) -> None:
        with mock.patch.object(config, "load_config", return_value={}), mock.patch.object(net, "http_get") as fetch:
            self.store.load_homebrews()

        fetch.assert_not_called()
        self.assertIn("not configured", self.store.homebrew_snapshot().error)

    def test_concurrent_refresh_does_not_start_another_request(self) -> None:
        self.store.homebrew_loading = True

        with mock.patch.object(net, "http_get") as fetch:
            self.store.load_homebrews(force=True)

        fetch.assert_not_called()

    def test_view_setting_is_saved_independently(self) -> None:
        self.store.set_homebrews_view(view="grid")
        reloaded = Vault(base=self.base)
        self.assertEqual(reloaded.homebrews_view, "grid")
        self.assertEqual(reloaded.ports_view, "list")


class HomebrewConfigTests(unittest.TestCase):
    def test_homebrews_feed_is_an_optional_environment_setting(self) -> None:
        self.assertIn(HOMEBREWS_KEY, config.OPTIONAL_KEYS)

        with mock.patch.dict(os.environ, {HOMEBREWS_KEY: "https://example.com/homebrews.json"}):
            self.assertEqual(config.load_config()[HOMEBREWS_KEY], "https://example.com/homebrews.json")
