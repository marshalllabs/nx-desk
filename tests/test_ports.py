import json
import tempfile
import unittest
from typing import List
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
        patches = mock.patch.object(target=settings, attribute="load_config", return_value={settings.PORTS_KEY: url})

        with patches, mock.patch.object(target=net, attribute="http_get", return_value=response) as fetch:
            self.store.load_ports(force=force)

        return fetch

    def test_keeps_good_rows_and_cleans_their_fields(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual(first=[row.id for row in rows], second=["a/spider", "b/armsx2"])
        self.assertEqual(first=rows[0].host, second="github")
        self.assertEqual(first=rows[0].thread, second="https://gbatemp.test/t/1")
        self.assertEqual(first=(rows[1].kind, rows[1].emulates), second=("emulator", "PS2"))
        # Only HTTPS links are kept, and a missing platform gets a name.
        self.assertEqual(first=rows[1].url, second="")
        self.assertEqual(first=parse_ports(data={"ports": [{"id": "x/y", "name": "Y"}]})[0].platform, second="Other")

    def test_other_shapes_give_no_rows(self) -> None:
        shapes: List[object] = [None, [], {}, {"ports": "x"}, {"ports": {}}]

        for data in shapes:
            self.assertEqual(first=parse_ports(data=data), second=[])

    def test_search_needs_every_word_in_any_field(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual(
            first=[row.name for row in find_ports(rows=rows, query="spider android")],
            second=["Amazing Spider-Man 2"],
        )
        self.assertEqual(first=[row.name for row in find_ports(rows=rows, query="ps2")], second=["ARMSX2"])
        self.assertEqual(first=[row.name for row in find_ports(rows=rows, query="b/arm")], second=["ARMSX2"])
        self.assertEqual(
            first=[row.name for row in find_ports(rows=rows, query="complet")],
            second=["Amazing Spider-Man 2"],
        )
        self.assertEqual(first=find_ports(rows=rows, query="spider ps2"), second=[])
        self.assertEqual(first=len(find_ports(rows=rows, query="  ")), second=2)

    def test_platforms_are_counted_by_name(self) -> None:
        rows = parse_ports(data=self.DATA)
        self.assertEqual(first=platform_counts(rows=rows), second=[("Android 32bit", 1), ("Emulators", 1)])

    def test_status_marks_get_words_and_tones(self) -> None:
        self.assertEqual(first=status_label(status="🟩"), second="Completable")
        self.assertEqual(first=status_label(status="✳️"), second="Feature complete")
        self.assertEqual(first=status_label(status="Working"), second="Working")
        self.assertEqual(first=status_label(status=""), second="")
        self.assertEqual(
            first=(status_tone(status="⬛️"), status_tone(status="🟨"), status_tone(status="?")),
            second=("bad", "accent", "ink"),
        )
        self.assertEqual(
            first=(host_label(host="gitlab"), host_label(host="other"), host_label(host="")),
            second=("GitLab", "Other", ""),
        )

    def test_the_list_is_cached(self) -> None:
        self.assertEqual(first=self.load(data=self.DATA).call_count, second=1)
        snapshot = self.store.port_snapshot()
        self.assertEqual(first=(len(snapshot.rows), snapshot.error, snapshot.loading), second=(2, "", False))
        self.assertEqual(first=self.load(data=self.DATA).call_count, second=0)
        self.assertEqual(first=self.load(data=self.DATA, force=True).call_count, second=1)

    def test_a_restart_shows_the_cached_list_before_any_request(self) -> None:
        self.load(data=self.DATA)
        again = vault.Vault(base=self.store.base)
        self.assertEqual(first=[row.id for row in again.port_snapshot().rows], second=["a/spider", "b/armsx2"])

    def test_a_failed_refresh_keeps_the_list(self) -> None:
        self.load(data=self.DATA)
        self.load(data={"ports": []}, force=True)
        snapshot = self.store.port_snapshot()
        self.assertEqual(first=len(snapshot.rows), second=2)
        self.assertIn(member="empty", container=snapshot.error)

    def test_a_missing_or_insecure_link_is_reported(self) -> None:
        for url in ("", "http://x.test/ports.json"):
            self.assertEqual(first=self.load(data=self.DATA, url=url).call_count, second=0)
            self.assertIn(member=settings.PORTS_KEY, container=self.store.port_snapshot().error)

    def test_the_link_is_read_at_runtime_and_embedded_when_set(self) -> None:
        self.assertIn(member=settings.PORTS_KEY, container=settings.OPTIONAL_KEYS)
        self.assertNotIn(member=settings.PORTS_KEY, container=settings.CONFIG_KEYS)

        with mock.patch.dict(in_dict="os.environ", values={settings.PORTS_KEY: self.URL}):
            self.assertEqual(first=settings.load_config()[settings.PORTS_KEY], second=self.URL)
