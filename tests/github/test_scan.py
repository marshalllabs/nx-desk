from pathlib import Path

from tests.github.case import GitHubCase


class ScanTests(GitHubCase):
    def test_only_valid_mod_folders_are_scanned(self) -> None:
        src = self.fresh_source()
        self.mod(name="Good - [VI] - [1.0]", root=src)
        (src / "Empty - [VI] - [1.0]").mkdir()
        wrong = src / "Wrong - [VI] - [1.0]"
        wrong.mkdir()
        (wrong / "other.zip").write_bytes(data=b"x")
        self.store.scan_upload()
        self.assertEqual(first=[unit.name for unit in self.store.upload_job.folders], second=["Good - [VI] - [1.0]"])

    def test_invalid_mod_folders_are_shown_but_not_uploaded(self) -> None:
        src = self.fresh_source()
        self.mod(name="Good - [VI] - [1.0]", root=src)
        (src / "Empty - [VI] - [1.0]").mkdir()
        self.store.scan_upload()
        nodes = {node.name: node for node in self.store.upload_job.tree_nodes}
        self.assertEqual(first=sorted(nodes), second=["Empty - [VI] - [1.0]", "Good - [VI] - [1.0]"])
        self.assertTrue(expr=nodes["Empty - [VI] - [1.0]"].invalid)
        self.assertIsNone(obj=nodes["Empty - [VI] - [1.0]"].unit)
        self.assertEqual(first=[unit.name for unit in self.store.upload_job.folders], second=["Good - [VI] - [1.0]"])

    def test_a_release_named_like_a_catalog_uses_its_download_folder(self) -> None:
        self.store.set_download_dir(text=str(self.base / "downloads"))
        catalog_dir = self.base / "downloads" / "my-catalog"
        self.mod(name="Kirby - [VI] - [1.0]", root=catalog_dir)
        self.hub.releases = ["my-catalog", "reviewed"]
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="my-catalog")
        self.store.set_auto_repo(repo="me/mods")
        self.store.load_assets()
        job = self.store.upload_snapshot()
        self.assertEqual(first=Path(job.source), second=catalog_dir)
        self.assertEqual(first=job.source_list, second=1)
        self.assertEqual(first=[unit.name for unit in job.folders], second=["Kirby - [VI] - [1.0]"])
        self.assertIn(member="Source folder set to", container=job.message)

    def test_a_release_without_a_matching_folder_uses_the_destination(self) -> None:
        downloads = self.base / "downloads"
        self.store.set_download_dir(text=str(downloads))
        self.mod(name="Kirby - [VI] - [1.0]", root=downloads / "my-catalog")
        self.store.load_assets()
        job = self.store.upload_snapshot()
        self.assertEqual(first=Path(job.source), second=downloads)
        self.assertEqual(first=[unit.name for unit in job.folders], second=["Kirby - [VI] - [1.0]"])
        self.assertIsNone(obj=self.store.release_source(tag="../src"))

    def test_a_missing_destination_keeps_the_source(self) -> None:
        self.store.set_download_dir(text=str(self.base / "nowhere"))
        self.store.load_assets()
        job = self.store.upload_snapshot()
        self.assertEqual(first=job.source, second=str(self.src))
        self.assertEqual(first=job.source_list, second=0)

    def test_zip_may_leave_out_the_build_number(self) -> None:
        src = self.fresh_source()
        folder = src / "Ori - [VI] - [1.0.2-v131072]"
        folder.mkdir()
        (folder / "Ori - [VI] - [1.0.2].zip").write_bytes(data=b"zip")
        other = src / "Kirby - [VI] - [1.1.0-v65536]"
        other.mkdir()
        (other / "Kirby - [VI] - [1.0.0].zip").write_bytes(data=b"zip")
        self.store.scan_upload()
        nodes = {node.name: node for node in self.store.upload_job.tree_nodes}
        self.assertFalse(expr=nodes["Ori - [VI] - [1.0.2-v131072]"].invalid)
        self.assertTrue(expr=nodes["Kirby - [VI] - [1.1.0-v65536]"].invalid)
        self.assertEqual(
            first=[unit.name for unit in self.store.upload_job.folders],
            second=["Ori - [VI] - [1.0.2-v131072]"],
        )

    def test_a_scan_during_an_upload_keeps_each_folders_status(self) -> None:
        self.store.scan_upload()
        self.store._mark_folder(name="Hades - [VI] - [1.0]", status="working")
        self.store.scan_upload()
        folders = {folder.name: folder.status for folder in self.store.upload_snapshot().folders}
        self.assertEqual(first=folders["Hades - [VI] - [1.0]"], second="working")

    def test_a_mod_saved_under_the_source_appears_in_the_panel(self) -> None:
        self.store.scan_upload()
        self.mod(name="Kirby - [VI] - [1.0]")
        self.store._source_changed(path=self.src / "Kirby - [VI] - [1.0]")
        names = [folder.name for folder in self.store.upload_snapshot().folders]
        self.assertIn(member="Kirby - [VI] - [1.0]", container=names)
        self.store._source_changed(path=self.base / "elsewhere" / "Game")

    def test_scan_finds_game_folders_recursively(self) -> None:
        src = self.fresh_source()
        self.mod(name="Game A - [VI] - [1.0]", root=src)
        self.mod(name="Game B - [VI] - [2.0]", root=src / "[On Switch]")
        (src / "[On Switch]" / "notes.txt").write_bytes(data=b"x")
        self.store.scan_upload()
        job = self.store.upload_job
        self.assertEqual(
            first=sorted(unit.name for unit in job.folders),
            second=["Game A - [VI] - [1.0]", "Game B - [VI] - [2.0]"],
        )
        top = {node.name: node for node in job.tree_nodes}
        self.assertEqual(first=sorted(top), second=["Game A - [VI] - [1.0]", "[On Switch]"])
        self.assertEqual(first=top["Game A - [VI] - [1.0]"].unit, second="Game A - [VI] - [1.0]")
        self.assertEqual(first=[c.name for c in top["[On Switch]"].children], second=["Game B - [VI] - [2.0]"])

    def test_container_without_game_folders_is_dropped(self) -> None:
        src = self.fresh_source()
        (src / "random" / "stuff").mkdir(parents=True)
        self.mod(name="Game - [VI] - [1.0]", root=src)
        self.store.scan_upload()
        self.assertEqual(first=[node.name for node in self.store.upload_job.tree_nodes], second=["Game - [VI] - [1.0]"])

    def test_github_log_groups_lines_by_game(self) -> None:
        self.store.scan_upload()
        self.store.upload_folders(names=["Hades - [VI] - [1.0]"])
        lines = [(line.game, line.text) for line in self.store.upload_snapshot().log]
        hades = [text for game, text in lines if game == "Hades"]
        self.assertTrue(expr=any("zipping" in text for text in hades))
        self.assertTrue(expr=any("uploaded in" in text for text in hades))
        self.assertTrue(expr=all(text.startswith("[VI] - [1.0]") for text in hades))
