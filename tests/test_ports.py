import json
import tempfile
import unittest
from unittest import mock

from nx_desk import config as settings
from nx_desk import net, vault
from nx_desk.catalog.ports import (
    find_ports,
    host_label,
    parse_ports,
    platform_counts,
    status_label,
    status_tone,
)


class PortListTests(unittest.TestCase):
    URL = "https://x.test/switch-ports.json"
    DATA = {
        "ports": [
            {
                "id": "a/spider",
                "name": "Amazing Spider-Man 2",
                "platform": "Android 32bit",
                "kind": "port",
                "version": "1.0.0",
                "updated": "2026-10-06",
                "url": "https://github.com/a/spider",
                "host": "GitHub",
                "thread": "https://gbatemp.test/t/1",
                "status": "🟩",
            },
            {
                "id": "b/armsx2",
                "name": "ARMSX2",
                "platform": "Emulators",
                "kind": "emulator",
                "emulates": "PS2",
                "url": "http://insecure.test/b",
            },
            {"id": "a/spider", "name": "Duplicate id"},
            {"id": "", "name": "No id"},
            {"id": "c/noname", "name": "  "},
            "not a row",
        ],
    }

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = vault.Vault(base=folder.name)

    def load(self, data: object, url: str = URL, force: bool = False) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(obj=data).encode()
        patches = mock.patch.object(settings, "load_config", return_value={settings.PORTS_KEY: url})

        with patches, mock.patch.object(net, "http_get", return_value=response) as fetch:
            self.store.load_ports(force=force)

        return fetch

    def test_keeps_good_rows_and_cleans_their_fields(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual([row.id for row in rows], ["a/spider", "b/armsx2"])
        self.assertEqual(rows[0].host, "github")
        self.assertEqual(rows[0].thread, "https://gbatemp.test/t/1")
        self.assertEqual((rows[1].kind, rows[1].emulates), ("emulator", "PS2"))
        # Only HTTPS links are kept, and a missing platform gets a name.
        self.assertEqual(rows[1].url, "")
        self.assertEqual(parse_ports(data={"ports": [{"id": "x/y", "name": "Y"}]})[0].platform, "Other")

    def test_other_shapes_give_no_rows(self) -> None:
        shapes: list[object] = [None, [], {}, {"ports": "x"}, {"ports": {}}]

        for data in shapes:
            self.assertEqual(parse_ports(data=data), [])

    def test_search_needs_every_word_in_any_field(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual([row.name for row in find_ports(rows=rows, query="spider android")], ["Amazing Spider-Man 2"])
        self.assertEqual([row.name for row in find_ports(rows=rows, query="ps2")], ["ARMSX2"])
        self.assertEqual([row.name for row in find_ports(rows=rows, query="b/arm")], ["ARMSX2"])
        self.assertEqual([row.name for row in find_ports(rows=rows, query="complet")], ["Amazing Spider-Man 2"])
        self.assertEqual(find_ports(rows=rows, query="spider ps2"), [])
        self.assertEqual(len(find_ports(rows=rows, query="  ")), 2)

    def test_platforms_are_counted_by_name(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual(platform_counts(rows=rows), [("Android 32bit", 1), ("Emulators", 1)])

    def test_status_marks_get_words_and_tones(self) -> None:
        self.assertEqual(status_label(status="🟩"), "Completable")
        self.assertEqual(status_label(status="✳️"), "Feature complete")
        self.assertEqual(status_label(status="Working"), "Working")
        self.assertEqual(status_label(status=""), "")
        self.assertEqual(
            (status_tone(status="⬛️"), status_tone(status="🟨"), status_tone(status="?")),
            ("bad", "accent", "ink"),
        )
        self.assertEqual(
            (host_label(host="gitlab"), host_label(host="other"), host_label(host="")),
            ("GitLab", "Other", ""),
        )

    def test_the_list_is_cached(self) -> None:
        self.assertEqual(self.load(data=self.DATA).call_count, 1)
        snapshot = self.store.port_snapshot()
        self.assertEqual((len(snapshot.rows), snapshot.error, snapshot.loading), (2, "", False))
        self.assertEqual(self.load(data=self.DATA).call_count, 0)
        self.assertEqual(self.load(data=self.DATA, force=True).call_count, 1)

    def test_a_restart_shows_the_cached_list_before_any_request(self) -> None:
        self.load(data=self.DATA)
        again = vault.Vault(base=self.store.base)
        self.assertEqual([row.id for row in again.port_snapshot().rows], ["a/spider", "b/armsx2"])

    def test_a_failed_refresh_keeps_the_list(self) -> None:
        self.load(data=self.DATA)
        self.load(data={"ports": []}, force=True)
        snapshot = self.store.port_snapshot()
        self.assertEqual(len(snapshot.rows), 2)
        self.assertIn("empty", snapshot.error)

    def test_a_missing_or_insecure_link_is_reported(self) -> None:
        for url in ("", "http://x.test/ports.json"):
            self.assertEqual(self.load(data=self.DATA, url=url).call_count, 0)
            self.assertIn(settings.PORTS_KEY, self.store.port_snapshot().error)

    def test_the_link_is_read_at_runtime_and_embedded_when_set(self) -> None:
        self.assertIn(settings.PORTS_KEY, settings.OPTIONAL_KEYS)
        self.assertNotIn(settings.PORTS_KEY, settings.CONFIG_KEYS)

        with mock.patch.dict("os.environ", {settings.PORTS_KEY: self.URL}):
            self.assertEqual(settings.load_config()[settings.PORTS_KEY], self.URL)
