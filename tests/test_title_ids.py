import json
import tempfile
import unittest
from unittest import mock

from nx_desk import config as settings
from nx_desk import net, vault
from nx_desk.catalog.title_ids import find_titles, parse_title_ids


class TitleIdTests(unittest.TestCase):
    URL = "https://x.test/title-ids.json"
    DATA = {
        "games": {
            "0100000000010000": "Super Mario Odyssey",
            "0100000000010800": "Super Mario Odyssey Update",
            "bad id": "Dropped",
            "0100000000011000": 5,
        },
        "system": {"0100000000001000": {"name": "qlaunch", "group": "System Applets"}},
        "sysmodules": {"430000000000000B": "sys-botbase"},
    }

    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = vault.Vault(base=folder.name)

    def load(self, data: object, url: str = URL, force: bool = False) -> mock.MagicMock:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(obj=data).encode()
        config = {settings.TITLE_IDS_KEY: url}
        patches = mock.patch.object(target=settings, attribute="load_config", return_value=config)

        with patches, mock.patch.object(target=net, attribute="http_get", return_value=response) as fetch:
            self.store.load_title_ids(force=force)

        return fetch

    def test_keeps_three_sections_and_drops_bad_rows(self) -> None:
        rows = parse_title_ids(data=self.DATA)
        self.assertEqual(first=[row.section for row in rows], second=["games", "games", "system", "sysmodules"])
        self.assertEqual(first=[row.detail for row in rows], second=["Game", "Update", "System Applets", "Homebrew"])
        self.assertEqual(first=parse_title_ids(data=["nope"]), second=[])

    def test_a_full_id_also_finds_the_game_but_never_a_system_neighbour(self) -> None:
        rows = parse_title_ids(data=self.DATA)
        found = find_titles(rows=rows, query="0100000000010800")
        self.assertEqual(first=[row.id for row in found], second=["0100000000010000", "0100000000010800"])
        self.assertEqual(
            first=[row.name for row in find_titles(rows=rows, query="0100000000001000")],
            second=["qlaunch"],
        )
        self.assertEqual(first=find_titles(rows=rows, query="0100000000000000"), second=[])
        self.assertEqual(first=[row.name for row in find_titles(rows=rows, query="BOTBASE")], second=["sys-botbase"])

    def test_the_list_is_cached_for_a_day(self) -> None:
        self.assertEqual(first=self.load(data=self.DATA).call_count, second=1)
        self.assertEqual(first=self.store.title_snapshot().error, second="")
        self.assertEqual(first=self.load(data=self.DATA).call_count, second=0)
        self.assertEqual(first=self.load(data=self.DATA, force=True).call_count, second=1)

    def test_a_failed_refresh_keeps_the_list(self) -> None:
        self.load(data=self.DATA)
        self.load(data={}, force=True)
        snapshot = self.store.title_snapshot()
        self.assertEqual(first=len(snapshot.rows), second=4)
        self.assertIn(member="empty", container=snapshot.error)

    def test_a_missing_link_is_reported(self) -> None:
        self.assertEqual(first=self.load(data=self.DATA, url="").call_count, second=0)
        self.assertIn(member=settings.TITLE_IDS_KEY, container=self.store.title_snapshot().error)
