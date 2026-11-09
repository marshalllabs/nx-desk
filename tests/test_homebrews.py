import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Tuple
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
        self.assertEqual(first=len(rows), second=1)
        self.assertEqual(first=rows[0].groups, second=["Applications", "Plugins"])
        self.assertEqual(first=rows[0].description, second="Manage local files")
        self.assertEqual(first=rows[0].authors, second="Example Author")

    def test_drops_invalid_entries_and_duplicate_ids(self) -> None:
        row = DATA["homebrews"][0]
        data = {"homebrews": [None, {}, {"id": "no-name"}, row, row]}
        self.assertEqual(first=len(parse_homebrews(data=data)), second=1)

    def test_sanitizes_links_and_groups(self) -> None:
        row = {**DATA["homebrews"][0], "url": "javascript:alert(1)", "groups": [None, 1, "Games", " Games "]}
        result = parse_homebrews(data={"homebrews": [row]})[0]
        self.assertEqual(first=result.url, second="")
        self.assertEqual(first=result.groups, second=["Games"])

    def test_search_matches_all_words_across_fields(self) -> None:
        rows = parse_homebrews(data=DATA)
        self.assertEqual(first=find_homebrews(rows=rows, query="files author plugins"), second=rows)
        self.assertEqual(first=find_homebrews(rows=rows, query="files missing"), second=[])
        self.assertEqual(first=find_homebrews(rows=rows, query=" "), second=rows)

    def test_invalid_document_shapes_are_empty(self) -> None:
        shapes: Tuple[object, ...] = (None, [], {}, {"homebrews": "invalid"})

        for shape in shapes:
            self.assertEqual(first=parse_homebrews(data=shape), second=[])


class HomebrewCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="homebrew-cache-")
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.store = Vault(base=self.base)
        self.path = self.store.cache_dir / HOMEBREWS_FILE
        self.raw = json.dumps(obj=DATA).encode()
        settings = mock.patch.object(
            target=config,
            attribute="load_config",
            return_value={HOMEBREWS_KEY: "https://example.com/feed.json"},
        )
        settings.start()
        self.addCleanup(settings.stop)

    def response(self, raw: bytes) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = raw

        return response

    def test_fetches_valid_data_and_reuses_fresh_cache(self) -> None:
        with mock.patch.object(target=net, attribute="http_get", return_value=self.response(raw=self.raw)) as fetch:
            self.store.load_homebrews()
            self.store.load_homebrews()

        self.assertEqual(first=fetch.call_count, second=1)
        self.assertEqual(first=self.path.read_bytes(), second=self.raw)
        self.assertEqual(first=len(self.store.homebrew_snapshot().rows), second=1)
        self.assertFalse(expr=self.store.homebrew_snapshot().loading)
        self.assertEqual(first=self.store.homebrew_snapshot().error, second="")

    def test_failed_refresh_keeps_cached_rows_and_file(self) -> None:
        self.path.write_bytes(data=self.raw)

        with mock.patch.object(target=net, attribute="http_get", side_effect=OSError("offline")):
            self.store.load_homebrews(force=True)

        snapshot = self.store.homebrew_snapshot()
        self.assertEqual(first=len(snapshot.rows), second=1)
        self.assertEqual(first=snapshot.error, second="offline")
        self.assertFalse(expr=snapshot.loading)
        self.assertEqual(first=self.path.read_bytes(), second=self.raw)

    def test_empty_and_invalid_responses_do_not_replace_cache(self) -> None:
        self.path.write_bytes(data=self.raw)

        for raw in (b'{"homebrews": []}', b"not JSON"):
            with mock.patch.object(target=net, attribute="http_get", return_value=self.response(raw=raw)):
                self.store.load_homebrews(force=True)

            self.assertEqual(first=self.path.read_bytes(), second=self.raw)
            self.assertTrue(expr=self.store.homebrew_snapshot().error)

    def test_oversized_response_is_rejected(self) -> None:
        with (
            mock.patch(target="nx_desk.vault.homebrews.MAX_CATALOG", new=10),
            mock.patch.object(
                target=net,
                attribute="http_get",
                return_value=self.response(raw=b"x" * 11),
            ),
        ):
            self.store.load_homebrews(force=True)

        self.assertIn(member="too large", container=self.store.homebrew_snapshot().error)
        self.assertFalse(expr=self.path.exists())

    def test_missing_feed_reports_configuration_error(self) -> None:
        with (
            mock.patch.object(target=config, attribute="load_config", return_value={}),
            mock.patch.object(target=net, attribute="http_get") as fetch,
        ):
            self.store.load_homebrews()

        fetch.assert_not_called()
        self.assertIn(member="not configured", container=self.store.homebrew_snapshot().error)

    def test_concurrent_refresh_does_not_start_another_request(self) -> None:
        self.store.homebrew_loading = True

        with mock.patch.object(target=net, attribute="http_get") as fetch:
            self.store.load_homebrews(force=True)

        fetch.assert_not_called()

    def test_view_setting_is_saved_independently(self) -> None:
        self.store.set_homebrews_view(view="grid")
        reloaded = Vault(base=self.base)
        self.assertEqual(first=reloaded.homebrews_view, second="grid")
        self.assertEqual(first=reloaded.ports_view, second="list")


class HomebrewConfigTests(unittest.TestCase):
    def test_homebrews_feed_is_an_optional_environment_setting(self) -> None:
        self.assertIn(member=HOMEBREWS_KEY, container=config.OPTIONAL_KEYS)

        with mock.patch.dict(in_dict=os.environ, values={HOMEBREWS_KEY: "https://example.com/homebrews.json"}):
            self.assertEqual(first=config.load_config()[HOMEBREWS_KEY], second="https://example.com/homebrews.json")
