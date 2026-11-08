from tests.auto_upload.case import AutoUploadCase


class GitHubTabTests(AutoUploadCase):
    def test_deleting_a_file_in_the_github_tab_updates_state_json(self) -> None:
        self.download(item=self.item())
        self.github_tab()
        self.store.delete_release_assets(names=["Game-VI-1-0.zip"])
        self.assertEqual(self.remote_state(), {})

    def test_an_upload_in_the_github_tab_records_known_mods(self) -> None:
        self.store.set_auto_upload(enabled=False)
        self.download(item=self.item())
        self.hub.releases.append("my-catalog")
        self.store.set_auto_upload(enabled=True)
        self.github_tab()
        self.store.upload_folders(names=["Game - [VI] - [1.0]"])
        self.assertEqual(self.remote_state()["game"]["sha256"], "a" * 64)

    def test_uploads_from_both_tabs_carry_the_folder_name_as_label(self) -> None:
        self.download(item=self.item())
        self.assertEqual(self.hub.assets["Game-VI-1-0.zip"]["label"], "Game - [VI] - [1.0]")
        self.github_tab()
        self.store.upload_folders(names=["Game - [VI] - [1.0]"])
        self.assertEqual(self.hub.assets["Game-VI-1-0.zip"]["label"], "Game - [VI] - [1.0]")

    def test_state_json_stays_out_of_the_github_tab(self) -> None:
        self.download(item=self.item())
        self.github_tab()
        self.store.load_assets()
        self.assertEqual([asset.name for asset in self.store.upload_snapshot().assets], ["Game-VI-1-0.zip"])

    def test_renaming_a_linked_release_leaves_only_local_copies(self) -> None:
        self.store.set_auto_delete(enabled=True)
        item = self.item()
        self.download(item=item)
        self.github_tab()
        self.store.rename_release(new_tag="renamed")
        self.assertEqual(self.store.status_of(entry=item), "missing")
