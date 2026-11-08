import json
import unittest

from nx_desk import config as settings
from nx_desk.catalog.fields import CATALOG_TEMPLATE
from nx_desk.catalog.parse import parse_catalog


class CatalogTemplateTests(unittest.TestCase):
    def test_every_field_of_the_template_is_read_without_a_mapping(self) -> None:
        item = parse_catalog(data=json.loads(s=json.dumps(obj=CATALOG_TEMPLATE))).items[0]
        self.assertEqual(item.id, "example-game")
        self.assertEqual(item.version, "v1")
        self.assertEqual(len(item.urls), 2)

        values: dict[str, object] = dict(item)

        for field in ("title_id", "game_version", "tagline", "developer", "release", "translator", "changelog"):
            self.assertTrue(values[field], field)

        for field in ("tags", "description", "highlights", "done", "kept", "cover", "background", "credit"):
            self.assertTrue(values[field], field)

        self.assertEqual(item.size, 12345678)
        self.assertRegex(item.title_id, settings.TITLE_ID)

    def test_the_template_is_only_the_games_list(self) -> None:
        self.assertEqual(list(CATALOG_TEMPLATE), ["mods"])

    def test_a_catalog_needs_only_an_id_and_an_https_url_for_each_mod(self) -> None:
        data = {"mods": [{"id": "example-game", "name": "Example Game", "url": "https://example.com/example-game.zip"}]}
        item = parse_catalog(data=data).items[0]
        self.assertEqual(item.id, "example-game")
        self.assertEqual(len(item.urls), 1)
