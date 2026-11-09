import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import List

from nx_desk import vault
from nx_desk.vault.layout import migrate_layout
from tests.helpers import entry

GRID = "https://cdn2.steamgriddb.com/grid/abc.png"
HERO = "https://cdn2.steamgriddb.com/hero/def.jpg"


def digest(url: str) -> str:
    return hashlib.sha256(string=url.encode(encoding="utf-8")).hexdigest()[:8]


def write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data=data if isinstance(data, str) else json.dumps(obj=data), encoding="utf-8")


def tree(base: Path) -> List[str]:
    return sorted(str(path.relative_to(base)) for path in base.rglob(pattern="*"))


# A data folder as the first versions made it: everything flat in .catalogs/, an art index for each folder of art.
class OldLayoutCase(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name).resolve()
        old = self.base / ".catalogs"
        settings = {
            "active": "a",
            "catalogs": [{"name": "A", "url": "https://a.test/c.json", "folder": "a"}],
            "mod_name": "VI",
        }
        write(path=old / "index.json", data=settings)
        write(path=old / "a.json", data={"mods": [entry(id="one", name="One")]})
        write(
            path=old / "a.state.json",
            data={"one": {"file": "One - [VI] - [1.0]/One - [VI] - [1.0].zip", "sha256": "ab"}},
        )
        write(path=old / "a.release.json", data={"repo": "me/rel", "tag": "a"})
        write(
            path=old / "a.covers.json",
            data={"one-cover.png": GRID, "one-background.jpg": HERO, "gone-cover.png": GRID},
        )
        write(path=old / "_title_ids.json", data={"games": {}})
        write(path=old / "_ports.json", data={"ports": []})
        write(path=old / "_steamgriddb.json", data={})
        write(path=old / "_ports.covers.json", data={"tool-cover.png": GRID})
        write(path=old / "_none.covers.json", data={})
        write(path=old / "preserved.bin", data="00" * 32)
        write(path=self.base / "covers" / "a" / "one-cover.png", data="cover")
        write(path=self.base / "covers" / "a" / "one-background.jpg", data="hero")
        write(path=self.base / "covers" / "_ports" / "tool-cover.png", data="tool")
        (self.base / "covers" / "_none").mkdir()
        write(path=self.base / "downloaded" / "a" / "mod.zip", data="zip")


class MigrationTests(OldLayoutCase):
    def test_everything_moves_to_the_new_layout(self) -> None:
        migrate_layout(base=self.base)
        old = self.base / ".catalogs"
        self.assertTrue(expr=(self.base / "settings.json").is_file())
        self.assertFalse(expr=(old / "index.json").exists())

        for name in ("title_ids.json", "ports.json", "steamgriddb.json"):
            self.assertTrue(expr=(self.base / "cache" / name).is_file(), msg=name)

        for name in ("catalog.json", "state.json", "release.json"):
            self.assertTrue(expr=(old / "a" / name).is_file(), msg=name)

        # Only the catalog's folder and the unrelated sentinel file are left in .catalogs/.
        self.assertEqual(first=sorted(path.name for path in old.iterdir()), second=["a", "preserved.bin"])
        self.assertEqual(first=list(self.base.rglob(pattern="*.covers.json")), second=[])

    def test_art_keeps_its_content_under_a_name_with_its_urls_digest(self) -> None:
        migrate_layout(base=self.base)
        art = self.base / "covers" / "a"
        self.assertEqual(first=(art / f"one-cover.{digest(url=GRID)}.png").read_text(encoding="utf-8"), second="cover")
        self.assertEqual(
            first=(art / f"one-background.{digest(url=HERO)}.jpg").read_text(encoding="utf-8"),
            second="hero",
        )
        self.assertEqual(
            first=sorted(path.name for path in art.iterdir()),
            second=[f"one-background.{digest(url=HERO)}.jpg", f"one-cover.{digest(url=GRID)}.png"],
        )
        ports = self.base / "covers" / "_ports"
        self.assertEqual(first=[path.name for path in ports.iterdir()], second=[f"tool-cover.{digest(url=GRID)}.png"])

    def test_the_empty_leftovers_for_no_catalog_go(self) -> None:
        migrate_layout(base=self.base)
        self.assertFalse(expr=(self.base / "covers" / "_none").exists())
        self.assertFalse(expr=(self.base / ".catalogs" / "_none.covers.json").exists())

    def test_downloads_and_unrelated_files_are_not_touched(self) -> None:
        migrate_layout(base=self.base)
        self.assertEqual(first=(self.base / "downloaded" / "a" / "mod.zip").read_text(encoding="utf-8"), second="zip")
        self.assertEqual(
            first=(self.base / ".catalogs" / "preserved.bin").read_text(encoding="utf-8"),
            second="00" * 32,
        )

    def test_running_it_again_changes_nothing(self) -> None:
        migrate_layout(base=self.base)
        first = tree(base=self.base)
        migrate_layout(base=self.base)
        self.assertEqual(first=tree(base=self.base), second=first)

    def test_a_file_already_in_place_is_not_overwritten(self) -> None:
        write(path=self.base / "settings.json", data={"mod_name": "NEW"})
        migrate_layout(base=self.base)
        self.assertEqual(
            first=json.loads(s=(self.base / "settings.json").read_text(encoding="utf-8"))["mod_name"],
            second="NEW",
        )
        # The older copy stays, so nothing is lost when both exist.
        self.assertTrue(expr=(self.base / ".catalogs" / "index.json").is_file())

    def test_a_folder_without_catalogs_is_left_alone(self) -> None:
        empty = self.base / "empty"
        empty.mkdir()
        migrate_layout(base=empty)
        self.assertEqual(first=tree(base=empty), second=[])


class OpeningAnOldFolderTests(OldLayoutCase):
    def test_the_app_reads_its_settings_catalog_and_records_after_the_move(self) -> None:
        store = vault.Vault(base=self.base)
        self.assertEqual(first=(store.mod_name, store.catalog.name if store.catalog else None), second=("VI", "A"))
        self.assertEqual(first=[item.id for item in store.items], second=["one"])
        self.assertEqual(first=list(store.state), second=["one"])
        self.assertEqual(first=store.release_state.repo, second="me/rel")
        self.assertEqual(first=store.registry_path, second=self.base / "settings.json")

    def test_saving_writes_the_new_files_and_leaves_no_old_ones(self) -> None:
        store = vault.Vault(base=self.base)
        store.set_mod_name(name="EN")
        self.assertEqual(
            first=json.loads(s=(self.base / "settings.json").read_text(encoding="utf-8"))["mod_name"],
            second="EN",
        )
        self.assertFalse(expr=(self.base / ".catalogs" / "index.json").exists())
        self.assertEqual(first=vault.Vault(base=self.base).mod_name, second="EN")

    def test_a_new_folder_gets_the_new_layout_from_the_start(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = vault.Vault(base=folder.name)
        store.set_mod_name(name="VI")
        self.assertEqual(
            first=sorted(path.name for path in Path(folder.name).iterdir()),
            second=[".catalogs", "cache", "settings.json"],
        )


class RemovingACatalogTests(OldLayoutCase):
    def test_its_saved_data_and_art_go_and_the_downloads_stay(self) -> None:
        store = vault.Vault(base=self.base)
        store.remove_catalog(folder="a")
        self.assertFalse(expr=(self.base / ".catalogs" / "a").exists())
        self.assertFalse(expr=(self.base / "covers" / "a").exists())
        self.assertTrue(expr=(self.base / "downloaded" / "a" / "mod.zip").is_file())
        self.assertEqual(first=vault.Vault(base=self.base).catalogs, second=[])
