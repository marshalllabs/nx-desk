import json
import tempfile
import unittest
from pathlib import Path
from typing import ContextManager, Dict, Iterable, Optional
from unittest import mock

from nx_desk import net, uploader, vault
from nx_desk.schemas.catalog import Catalog, CatalogEdit
from tests.helpers import FakeGitHub, entry


def active(store: vault.Vault) -> Catalog:
    assert store.catalog is not None

    return store.catalog


class CatalogCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.store = vault.Vault(base=self.dir)

    def served(self, games: Iterable[str]) -> ContextManager[mock.Mock]:
        raw = json.dumps(obj={"mods": [entry(id=game, name=game.title()) for game in games]}).encode()
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = raw

        return mock.patch.object(target=net, attribute="http_get", return_value=response)

    def add(self, name: str, url: str, games: Iterable[str] = ("one",)) -> Catalog:
        with self.served(games=games):
            return self.store.add_catalog(name=name, url=url)

    def edit(
        self,
        folder: str,
        url: str,
        games: Iterable[str] = ("one",),
        name: str = "",
        mapping: Optional[Dict[str, str]] = None,
        github: Optional[FakeGitHub] = None,
    ) -> CatalogEdit:
        # Without a GitHub of its own, a test has no gh, so renaming never reaches the real one.
        fake = github or FakeGitHub()
        fake.logged_in = fake.logged_in if github else False

        with (
            self.served(games=games),
            mock.patch.object(target=uploader.api, attribute="request", new=fake.request),
            mock.patch.object(target=uploader.api, attribute="pages", new=fake.pages),
        ):
            return self.store.edit_catalog(folder=folder, name=name, url=url, mapping=mapping)
