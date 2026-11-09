from typing import List, Optional

from nx_desk import uploader, vault
from nx_desk.schemas.catalog import CatalogEdit
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
        (self.store.root / "game.zip").write_bytes(data=b"zip")
        self.store.art_dir.mkdir(parents=True)
        (self.store.art_dir / "cover.png").write_bytes(data=b"png")
        (self.dir / ".catalogs" / "a" / "state.json").write_text(data="{}", encoding="utf-8")
        self.store._write_json(path=self.store._release_cache(folder="a"), value=ReleaseState(repo=REPO, tag="a"))

    def rename(self, name: str = "Brand New", github: Optional[FakeGitHub] = None) -> CatalogEdit:
        return self.edit(folder="a", url="https://a.test/c.json", name=name, github=github or self.github)

    def test_a_new_name_renames_the_release_and_the_folder_with_everything_in_it(self) -> None:
        result = self.rename()
        self.assertEqual(first=result.catalog.folder, second="brand-new")
        self.assertEqual(
            first=result.notes,
            second=[f"Renamed the release to brand-new in {REPO} and removed its old tag a."],
        )
        self.assertEqual(first=self.github.releases, second=["brand-new", "other"])
        # GitHub keeps the old tag after a rename, so the app removes it: no tag is left without a release.
        self.assertEqual(first=self.github.tags, second={"brand-new", "other"})
        self.assertTrue(expr=(self.dir / ".catalogs" / "brand-new" / "catalog.json").is_file())
        self.assertTrue(expr=(self.dir / ".catalogs" / "brand-new" / "state.json").is_file())
        self.assertFalse(expr=(self.dir / ".catalogs" / "a").exists())
        self.assertTrue(expr=(self.store.root / "game.zip").is_file())
        self.assertEqual(first=self.store.root.name, second="brand-new")
        self.assertTrue(expr=(self.dir / "covers" / "brand-new" / "cover.png").is_file())
        self.assertFalse(expr=(self.dir / "covers" / "a").exists())

    def test_the_catalog_stays_active_and_linked_after_a_restart(self) -> None:
        self.rename()
        self.assertEqual(first=self.store.release_state.tag, second="brand-new")
        self.assertIsNotNone(obj=self.store.linked_catalog(tag="brand-new"))
        self.assertIsNone(obj=self.store.linked_catalog(tag="a"))
        reopened = vault.Vault(base=self.dir)
        assert reopened.catalog is not None
        self.assertEqual(first=(reopened.catalog.folder, reopened.catalog.name), second=("brand-new", "Brand New"))
        self.assertEqual(first=reopened.release_state.tag, second="brand-new")
        self.assertEqual(first=len(reopened.items), second=1)

    def test_every_repository_with_the_release_is_renamed(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        result = self.rename()
        self.assertEqual(first=len(result.notes), second=2)
        self.assertEqual(first=self.store.upload_tag, second="brand-new")

    def test_the_github_tab_follows_when_its_repository_was_renamed(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        self.store.upload_job.releases = ["a", "other"]
        self.store.upload_job.latest_release = "a"
        before = self.store.upload_job.release_list
        self.rename()
        self.assertEqual(first=self.store.upload_job.releases, second=["brand-new", "other"])
        self.assertEqual(first=self.store.upload_job.latest_release, second="brand-new")
        self.assertGreater(a=self.store.upload_job.release_list, b=before)

    def test_a_tag_that_is_already_gone_counts_as_removed(self) -> None:
        self.github.tags = {"other"}
        result = self.rename()
        self.assertIn(member="removed its old tag a", container=result.notes[0])

    def test_a_tag_github_will_not_delete_is_reported_and_the_rename_stands(self) -> None:
        self.github.keep_tags = True
        result = self.rename()
        self.assertEqual(first=result.catalog.folder, second="brand-new")
        self.assertEqual(first=self.github.releases, second=["brand-new", "other"])
        self.assertIn(member="old tag a could not be removed", container=result.notes[0])

    def test_without_a_release_the_folder_still_follows_the_name(self) -> None:
        self.github.releases = ["other"]
        result = self.rename()
        self.assertEqual(first=(result.catalog.folder, result.notes), second=("brand-new", []))
        self.assertEqual(first=self.github.releases, second=["other"])

    def test_a_release_name_already_taken_changes_nothing(self) -> None:
        self.github.releases = ["a", "brand-new"]

        with self.assertRaises(expected_exception=ValueError) as caught:
            self.rename()

        self.assertIn(member="already has a release named brand-new", container=str(caught.exception))
        self.assertEqual(first=self.github.releases, second=["a", "brand-new"])
        self.assertEqual(first=(self.store.catalogs[0].folder, self.store.catalogs[0].name), second=("a", "A"))
        self.assertTrue(expr=(self.store.root / "game.zip").is_file())

    def test_a_failure_part_way_puts_the_first_release_back(self) -> None:
        self.store.set_upload_settings(source="", repo=TAB_REPO, tag="a")
        edits: List[str] = []

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

        with self.assertRaises(expected_exception=ValueError) as caught:
            self.rename(github=failing)

        self.assertIn(member="could not rename the release", container=str(caught.exception))
        # The first one was renamed, then renamed back, and the tag that made left again; the repository is as it was.
        self.assertEqual(first=failing.releases, second=["a", "other"])
        self.assertEqual(first=failing.tags, second={"a", "other"})
        self.assertEqual(first=(self.store.catalogs[0].folder, self.store.catalogs[0].name), second=("a", "A"))
        self.assertTrue(expr=(self.dir / ".catalogs" / "a" / "catalog.json").is_file())

    def test_a_folder_already_on_disk_keeps_the_old_name_and_the_release_untouched(self) -> None:
        (self.dir / ".catalogs" / "brand-new").mkdir()
        result = self.rename()
        self.assertEqual(first=(result.catalog.folder, result.catalog.name), second=("a", "Brand New"))
        self.assertIn(member="already used", container=result.notes[0])
        self.assertEqual(first=(self.github.releases, self.github.tags), second=(["a", "other"], {"a", "other"}))

    def test_without_gh_only_the_name_changes(self) -> None:
        self.github.logged_in = False
        result = self.rename()
        self.assertEqual(first=(result.catalog.folder, result.catalog.name), second=("a", "Brand New"))
        self.assertIn(member="gh is not available", container=result.notes[0])
        self.assertEqual(first=self.github.releases, second=["a", "other"])

    def test_a_name_with_the_same_slug_moves_nothing_and_asks_nothing_of_gh(self) -> None:
        self.github.logged_in = False
        result = self.rename(name="a!")
        self.assertEqual(first=(result.catalog.folder, result.catalog.name, result.notes), second=("a", "a!", []))

    def test_a_name_whose_folder_belongs_to_another_catalog_gets_a_numbered_one(self) -> None:
        self.add(name="B", url="https://b.test/c.json")
        self.store.select_catalog(folder="a")
        result = self.rename(name="B")
        self.assertEqual(first=result.catalog.folder, second="b-2")
        self.assertEqual(first=self.github.releases, second=["b-2", "other"])
        self.assertEqual(first=self.github.tags, second={"b-2", "other"})

    def test_an_inactive_catalog_is_renamed_too(self) -> None:
        self.add(name="B", url="https://b.test/c.json")
        self.assertEqual(first=self.store.catalog.name, second="B")  # type: ignore[union-attr]
        result = self.rename()
        self.assertEqual(first=result.catalog.folder, second="brand-new")
        self.assertEqual(first=self.store.catalog.folder, second="b")  # type: ignore[union-attr]
        self.assertTrue(expr=(self.dir / ".catalogs" / "brand-new" / "catalog.json").is_file())
        self.assertEqual(first=self.github.releases, second=["brand-new", "other"])
