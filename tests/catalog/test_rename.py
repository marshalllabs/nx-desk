from typing import Any

from nx_desk import uploader, vault
from nx_desk.schemas.state import ReleaseState
from tests.catalog.case import CatalogCase
from tests.helpers import FakeGitHub

REPO = "me/mod-releases"
TAB_REPO = "me/other-releases"


class RenameTests(CatalogCase):
    def setUp(self) -> None:
        super().setUp()
        self.add(name="A", url="https://a.test/c.json")
        self.store.set_auto_repo(repo=REPO)
        self.github = FakeGitHub()
        self.github.releases = ["a", "other"]
        self.github.tags = {"a", "other"}
        self.store.root.mkdir(parents=True)
        (self.store.root / "game.zip").write_bytes(b"zip")
        self.store.art_dir.mkdir(parents=True)
        (self.store.art_dir / "cover.png").write_bytes(b"png")
        (self.dir / ".catalogs" / "a" / "state.json").write_text("{}", encoding="utf-8")
        self.store._write_json(path=self.store._release_cache(folder="a"), value=ReleaseState(repo=REPO, tag="a"))

    def rename(self, name: str = "Brand New", github: FakeGitHub | None = None) -> Any:
        return self.edit(folder="a", url="https://a.test/c.json", name=name, github=github or self.github)

    def test_a_new_name_renames_the_release_and_the_folder_with_everything_in_it(self) -> None:
        result = self.rename()
        self.assertEqual(result.catalog.folder, "brand-new")
        self.assertEqual(result.notes, [f"Renamed the release to brand-new in {REPO} and removed its old tag a."])
        self.assertEqual(self.github.releases, ["brand-new", "other"])
        # GitHub keeps the old tag after a rename, so the app removes it: no tag is left without a release.
        self.assertEqual(self.github.tags, {"brand-new", "other"})
        self.assertTrue((self.dir / ".catalogs" / "brand-new" / "catalog.json").is_file())
        self.assertTrue((self.dir / ".catalogs" / "brand-new" / "state.json").is_file())
        self.assertFalse((self.dir / ".catalogs" / "a").exists())
        self.assertTrue((self.store.root / "game.zip").is_file())
        self.assertEqual(self.store.root.name, "brand-new")
        self.assertTrue((self.dir / "covers" / "brand-new" / "cover.png").is_file())
        self.assertFalse((self.dir / "covers" / "a").exists())

    def test_the_catalog_stays_active_and_linked_after_a_restart(self) -> None:
        self.rename()
        self.assertEqual(self.store.release_state.tag, "brand-new")
        self.assertIsNotNone(self.store.linked_catalog(tag="brand-new"))
        self.assertIsNone(self.store.linked_catalog(tag="a"))
        reopened = vault.Vault(base=self.dir)
        assert reopened.catalog is not None
        self.assertEqual((reopened.catalog.folder, reopened.catalog.name), ("brand-new", "Brand New"))
        self.assertEqual(reopened.release_state.tag, "brand-new")
        self.assertEqual(len(reopened.items), 1)

    def test_every_repository_with_the_release_is_renamed(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        result = self.rename()
        self.assertEqual(len(result.notes), 2)
        self.assertEqual(self.store.upload_tag, "brand-new")

    def test_the_github_tab_follows_when_its_repository_was_renamed(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        self.store.upload_job.releases = ["a", "other"]
        self.store.upload_job.latest_release = "a"
        before = self.store.upload_job.release_list
        self.rename()
        self.assertEqual(self.store.upload_job.releases, ["brand-new", "other"])
        self.assertEqual(self.store.upload_job.latest_release, "brand-new")
        self.assertGreater(self.store.upload_job.release_list, before)

    def test_a_tag_that_is_already_gone_counts_as_removed(self) -> None:
        self.github.tags = {"other"}
        result = self.rename()
        self.assertIn("removed its old tag a", result.notes[0])

    def test_a_tag_github_will_not_delete_is_reported_and_the_rename_stands(self) -> None:
        self.github.keep_tags = True
        result = self.rename()
        self.assertEqual(result.catalog.folder, "brand-new")
        self.assertEqual(self.github.releases, ["brand-new", "other"])
        self.assertIn("old tag a could not be removed", result.notes[0])

    def test_without_a_release_the_folder_still_follows_the_name(self) -> None:
        self.github.releases = ["other"]
        result = self.rename()
        self.assertEqual((result.catalog.folder, result.notes), ("brand-new", []))
        self.assertEqual(self.github.releases, ["other"])

    def test_a_release_name_already_taken_changes_nothing(self) -> None:
        self.github.releases = ["a", "brand-new"]

        with self.assertRaises(ValueError) as caught:
            self.rename()

        self.assertIn("already has a release named brand-new", str(caught.exception))
        self.assertEqual(self.github.releases, ["a", "brand-new"])
        self.assertEqual((self.store.catalogs[0].folder, self.store.catalogs[0].name), ("a", "A"))
        self.assertTrue((self.store.root / "game.zip").is_file())

    def test_a_failure_part_way_puts_the_first_release_back(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        edits: list[str] = []

        class Failing(FakeGitHub):
            def __call__(self, *args: str) -> str:
                if args[:2] == ("release", "edit"):
                    edits.append(args[2])

                    if len(edits) == 2:
                        raise uploader.command.GhError("HTTP 500")

                return super().__call__(*args)

        failing = Failing()
        failing.releases = ["a", "other"]
        failing.tags = {"a", "other"}

        with self.assertRaises(ValueError) as caught:
            self.rename(github=failing)

        self.assertIn("could not rename the release", str(caught.exception))
        # The first one was renamed, then renamed back, and the tag that made left again; the repository is as it was.
        self.assertEqual(failing.releases, ["a", "other"])
        self.assertEqual(failing.tags, {"a", "other"})
        self.assertEqual((self.store.catalogs[0].folder, self.store.catalogs[0].name), ("a", "A"))
        self.assertTrue((self.dir / ".catalogs" / "a" / "catalog.json").is_file())

    def test_a_folder_already_on_disk_keeps_the_old_name_and_the_release_untouched(self) -> None:
        (self.dir / ".catalogs" / "brand-new").mkdir()
        result = self.rename()
        self.assertEqual((result.catalog.folder, result.catalog.name), ("a", "Brand New"))
        self.assertIn("already used", result.notes[0])
        self.assertEqual((self.github.releases, self.github.tags), (["a", "other"], {"a", "other"}))

    def test_without_gh_only_the_name_changes(self) -> None:
        self.github.logged_in = False
        result = self.rename()
        self.assertEqual((result.catalog.folder, result.catalog.name), ("a", "Brand New"))
        self.assertIn("gh is not available", result.notes[0])
        self.assertEqual(self.github.releases, ["a", "other"])

    def test_a_name_with_the_same_slug_moves_nothing_and_asks_nothing_of_gh(self) -> None:
        self.github.logged_in = False
        result = self.rename(name="a!")
        self.assertEqual((result.catalog.folder, result.catalog.name, result.notes), ("a", "a!", []))

    def test_a_name_whose_folder_belongs_to_another_catalog_gets_a_numbered_one(self) -> None:
        self.add(name="B", url="https://b.test/c.json")
        self.store.select_catalog(folder="a")
        result = self.rename(name="B")
        self.assertEqual(result.catalog.folder, "b-2")
        self.assertEqual(self.github.releases, ["b-2", "other"])
        self.assertEqual(self.github.tags, {"b-2", "other"})

    def test_an_inactive_catalog_is_renamed_too(self) -> None:
        self.add(name="B", url="https://b.test/c.json")
        self.assertEqual(self.store.catalog.name, "B")  # type: ignore[union-attr]
        result = self.rename()
        self.assertEqual(result.catalog.folder, "brand-new")
        self.assertEqual(self.store.catalog.folder, "b")  # type: ignore[union-attr]
        self.assertTrue((self.dir / ".catalogs" / "brand-new" / "catalog.json").is_file())
        self.assertEqual(self.github.releases, ["brand-new", "other"])
