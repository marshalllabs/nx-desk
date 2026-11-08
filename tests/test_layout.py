import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from nx_desk import vault
from nx_desk.vault.layout import migrate_layout
from tests.helpers import entry

GRID = "https://cdn2.steamgriddb.com/grid/abc.png"
HERO = "https://cdn2.steamgriddb.com/hero/def.jpg"


def digest(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


def write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(obj=data), encoding="utf-8")


def tree(base: Path) -> list[str]:
    return sorted(str(path.relative_to(base)) for path in base.rglob("*"))


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
        write(old / "index.json", settings)
        write(old / "a.json", {"mods": [entry(id="one", name="One")]})
        write(old / "a.state.json", {"one": {"file": "One - [VI] - [1.0]/One - [VI] - [1.0].zip", "sha256": "ab"}})
        write(old / "a.release.json", {"repo": "me/rel", "tag": "a"})
        write(old / "a.covers.json", {"one-cover.png": GRID, "one-background.jpg": HERO, "gone-cover.png": GRID})
        write(old / "_title_ids.json", {"games": {}})
        write(old / "_ports.json", {"ports": []})
        write(old / "_steamgriddb.json", {})
        write(old / "_ports.covers.json", {"tool-cover.png": GRID})
        write(old / "_none.covers.json", {})
        write(old / "secret_key", "00" * 32)
        write(self.base / "covers" / "a" / "one-cover.png", "cover")
        write(self.base / "covers" / "a" / "one-background.jpg", "hero")
        write(self.base / "covers" / "_ports" / "tool-cover.png", "tool")
        (self.base / "covers" / "_none").mkdir()
        write(self.base / "downloaded" / "a" / "mod.zip", "zip")


class MigrationTests(OldLayoutCase):
    def test_everything_moves_to_the_new_layout(self) -> None:
        migrate_layout(base=self.base)
        old = self.base / ".catalogs"
        self.assertTrue((self.base / "settings.json").is_file())
        self.assertFalse((old / "index.json").exists())

        for name in ("title_ids.json", "ports.json", "steamgriddb.json"):
            self.assertTrue((self.base / "cache" / name).is_file(), name)

        for name in ("catalog.json", "state.json", "release.json"):
            self.assertTrue((old / "a" / name).is_file(), name)

        # Only the catalog's folder and the key that seals secrets are left in .catalogs/.
        self.assertEqual(sorted(path.name for path in old.iterdir()), ["a", "secret_key"])
        self.assertEqual(list(self.base.rglob("*.covers.json")), [])

    def test_art_keeps_its_content_under_a_name_with_its_urls_digest(self) -> None:
        migrate_layout(base=self.base)
        art = self.base / "covers" / "a"
        self.assertEqual((art / f"one-cover.{digest(GRID)}.png").read_text(encoding="utf-8"), "cover")
        self.assertEqual((art / f"one-background.{digest(HERO)}.jpg").read_text(encoding="utf-8"), "hero")
        self.assertEqual(
            sorted(path.name for path in art.iterdir()),
            [f"one-background.{digest(HERO)}.jpg", f"one-cover.{digest(GRID)}.png"],
        )
        ports = self.base / "covers" / "_ports"
        self.assertEqual([path.name for path in ports.iterdir()], [f"tool-cover.{digest(GRID)}.png"])

    def test_the_empty_leftovers_for_no_catalog_go(self) -> None:
        migrate_layout(base=self.base)
        self.assertFalse((self.base / "covers" / "_none").exists())
        self.assertFalse((self.base / ".catalogs" / "_none.covers.json").exists())

    def test_downloads_and_the_secret_key_are_not_touched(self) -> None:
        migrate_layout(base=self.base)
        self.assertEqual((self.base / "downloaded" / "a" / "mod.zip").read_text(encoding="utf-8"), "zip")
        self.assertEqual((self.base / ".catalogs" / "secret_key").read_text(encoding="utf-8"), "00" * 32)

    def test_running_it_again_changes_nothing(self) -> None:
        migrate_layout(base=self.base)
        first = tree(self.base)
        migrate_layout(base=self.base)
        self.assertEqual(tree(self.base), first)

    def test_a_file_already_in_place_is_not_overwritten(self) -> None:
        write(self.base / "settings.json", {"mod_name": "NEW"})
        migrate_layout(base=self.base)
        self.assertEqual(json.loads((self.base / "settings.json").read_text(encoding="utf-8"))["mod_name"], "NEW")
        # The older copy stays, so nothing is lost when both exist.
        self.assertTrue((self.base / ".catalogs" / "index.json").is_file())

    def test_a_folder_without_catalogs_is_left_alone(self) -> None:
        empty = self.base / "empty"
        empty.mkdir()
        migrate_layout(base=empty)
        self.assertEqual(tree(empty), [])


class OpeningAnOldFolderTests(OldLayoutCase):
    def test_the_app_reads_its_settings_catalog_and_records_after_the_move(self) -> None:
        store = vault.Vault(base=self.base)
        self.assertEqual((store.mod_name, store.catalog.name if store.catalog else None), ("VI", "A"))
        self.assertEqual([item.id for item in store.items], ["one"])
        self.assertEqual(list(store.state), ["one"])
        self.assertEqual(store.release_state.repo, "me/rel")
        self.assertEqual(store.registry_path, self.base / "settings.json")

    def test_saving_writes_the_new_files_and_leaves_no_old_ones(self) -> None:
        store = vault.Vault(base=self.base)
        store.set_mod_name(name="EN")
        self.assertEqual(json.loads((self.base / "settings.json").read_text(encoding="utf-8"))["mod_name"], "EN")
        self.assertFalse((self.base / ".catalogs" / "index.json").exists())
        self.assertEqual(vault.Vault(base=self.base).mod_name, "EN")

    def test_a_new_folder_gets_the_new_layout_from_the_start(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = vault.Vault(base=folder.name)
        store.set_mod_name(name="VI")
        self.assertEqual(
            sorted(path.name for path in Path(folder.name).iterdir()),
            [".catalogs", "cache", "settings.json"],
        )


class RemovingACatalogTests(OldLayoutCase):
    def test_its_saved_data_and_art_go_and_the_downloads_stay(self) -> None:
        store = vault.Vault(base=self.base)
        store.remove_catalog(folder="a")
        self.assertFalse((self.base / ".catalogs" / "a").exists())
        self.assertFalse((self.base / "covers" / "a").exists())
        self.assertTrue((self.base / "downloaded" / "a" / "mod.zip").is_file())
        self.assertEqual(vault.Vault(base=self.base).catalogs, [])
