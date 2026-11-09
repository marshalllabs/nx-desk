import json
import unittest
from typing import Dict

from nx_desk import config as settings
from nx_desk.catalog.fields import CATALOG_TEMPLATE
from nx_desk.catalog.parse import parse_catalog


class CatalogTemplateTests(unittest.TestCase):
    def test_every_field_of_the_template_is_read_without_a_mapping(self) -> None:
        item = parse_catalog(data=json.loads(s=json.dumps(obj=CATALOG_TEMPLATE.model_dump(mode="json")))).items[0]
        self.assertEqual(first=item.id, second="example-game")
        self.assertEqual(first=item.version, second="v1")
        self.assertEqual(first=len(item.urls), second=2)

        values: Dict[str, object] = item.model_dump()

        for field in ("title_id", "game_version", "tagline", "developer", "release", "translator", "changelog"):
            self.assertTrue(expr=values[field], msg=field)

        for field in ("tags", "description", "highlights", "done", "kept", "cover", "background", "credit"):
            self.assertTrue(expr=values[field], msg=field)

        self.assertEqual(first=item.size, second=12345678)
        self.assertRegex(text=item.title_id, expected_regex=settings.TITLE_ID)

    def test_the_template_is_only_the_games_list(self) -> None:
        self.assertEqual(first=list(type(CATALOG_TEMPLATE).model_fields), second=["mods"])

    def test_a_catalog_needs_only_an_id_and_an_https_url_for_each_mod(self) -> None:
        data = {"mods": [{"id": "example-game", "name": "Example Game", "url": "https://example.com/example-game.zip"}]}
        item = parse_catalog(data=data).items[0]
        self.assertEqual(first=item.id, second="example-game")
        self.assertEqual(first=len(item.urls), second=1)
