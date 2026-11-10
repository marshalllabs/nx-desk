from unittest import mock

from nx_desk import uploader, vault
from tests.github.case import GitHubCase


class ReleaseTests(GitHubCase):
    def test_opening_the_app_loads_everything_that_is_set(self) -> None:
        self.hub.add(name="Hades-VI-1-0.zip", digest="sha256:x")
        self.store.prepare_uploads()
        job = self.store.upload_job
        self.assertEqual(first=(len(job.folders), job.releases), second=(2, ["reviewed"]))
        self.assertEqual(first=[asset.name for asset in job.assets], second=["Hades-VI-1-0.zip"])

    def test_opening_the_app_without_a_login_stays_quiet(self) -> None:
        self.hub.logged_in = False
        self.store.prepare_uploads()
        job = self.store.upload_job
        self.assertEqual(first=job.alerts, second=0)
        self.assertTrue(expr=job.failed)
        self.assertEqual(first=len(job.folders), second=2)

    def test_opening_a_repo_selects_its_latest_release(self) -> None:
        self.hub.releases = ["unreviewed", "reviewed"]
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="unreviewed")
        self.store.load_releases()
        self.assertEqual(
            first=(self.store.upload_tag, self.store.upload_job.select_tag),
            second=("reviewed", "reviewed"),
        )

    def test_repo_without_a_latest_release_opens_the_first_one(self) -> None:
        self.hub.releases = ["a", "b"]
        self.hub.latest = ""
        self.store.load_releases()
        self.assertEqual(first=self.store.upload_tag, second="a")

    def test_repo_without_releases_clears_the_list(self) -> None:
        self.hub.releases = []
        self.hub.latest = ""
        self.hub.add(name="Old.zip", digest="sha256:x")
        self.store.load_releases()
        self.assertEqual(first=(self.store.upload_tag, self.store.upload_job.assets), second=("", []))

    def test_repo_list_is_sorted(self) -> None:
        self.store.reload_github()
        self.assertEqual(first=self.store.upload_job.repos, second=["Me/alpha", "me/zeta"])

    def test_opening_the_app_lists_repos_without_a_saved_one(self) -> None:
        self.store.set_upload_settings(source="", repo="", tag="")
        self.store.prepare_uploads()
        self.assertEqual(first=len(self.store.upload_job.repos), second=2)
        self.assertEqual(first=self.store.upload_job.releases, second=[])

    def test_new_release_is_not_marked_latest(self) -> None:
        with mock.patch.object(target=uploader.api, attribute="request", return_value=None) as call:
            uploader.releases.create_release(repo="me/mods", tag="new")

        self.assertEqual(first=call.call_args.kwargs["data"].make_latest, second="false")

    def test_not_logged_in_raises_an_alert(self) -> None:
        self.hub.logged_in = False
        self.store.load_releases()
        job = self.store.upload_job
        self.assertEqual(first=job.alerts, second=1)
        self.assertIn(member="Settings > GitHub", container=job.message)

    def test_refused_token_is_reported(self) -> None:
        with mock.patch.object(
            target=uploader.api,
            attribute="request",
            side_effect=uploader.command.GitHubError("HTTP 401: Token is invalid or expired."),
        ):
            self.store.load_releases()

        self.assertIn(member="invalid or expired", container=self.store.upload_job.message)

    def test_renames_the_current_release(self) -> None:
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="reviewed")
        self.store.rename_release(new_tag="checked")
        self.assertEqual(first=self.hub.releases, second=["checked"])
        self.assertEqual(first=self.store.upload_tag, second="checked")

    def test_delete_release_opens_another_one(self) -> None:
        self.hub.releases = ["reviewed", "draft"]
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="draft")
        self.store.delete_release()
        self.assertEqual(first=self.hub.releases, second=["reviewed"])
        self.assertEqual(first=self.store.upload_tag, second="reviewed")

    def test_delete_last_release_clears_the_list(self) -> None:
        self.store.set_upload_settings(source=str(self.src), repo="me/mods", tag="reviewed")
        self.store.delete_release()
        self.assertEqual(
            first=(self.hub.releases, self.store.upload_tag, self.store.upload_job.assets),
            second=([], "", []),
        )

    def test_lists_and_creates_releases(self) -> None:
        self.store.load_releases()
        self.assertEqual(first=self.store.upload_job.releases, second=["reviewed"])
        self.store.create_upload_release(tag="my-catalog")
        self.assertEqual(first=self.store.upload_job.releases, second=["reviewed", "my-catalog"])
        self.assertEqual(first=self.store.upload_job.select_tag, second="my-catalog")

    def test_rejects_a_bad_repo_name(self) -> None:
        self.store.set_upload_settings(source=str(self.src), repo="not a repo", tag="reviewed")
        self.store.load_releases()
        self.assertTrue(expr=self.store.upload_job.failed)

    def test_remembers_the_settings(self) -> None:
        again = vault.Vault(base=self.base / "data")
        self.assertEqual(first=(again.upload_repo, again.upload_tag), second=("me/mods", "reviewed"))


class ReleaseOrderTests(GitHubCase):
    def test_the_latest_comes_first_and_the_rest_by_name(self) -> None:
        self.hub.releases = ["b-mods", "newest", "A-mods"]
        self.hub.latest = "newest"
        self.store.load_releases()
        job = self.store.upload_job
        self.assertEqual(
            first=(job.releases, job.latest_release, job.select_tag),
            second=(["newest", "A-mods", "b-mods"], "newest", "newest"),
        )

    def test_without_a_latest_the_list_is_by_name(self) -> None:
        self.hub.releases = ["b-mods", "A-mods"]
        self.hub.latest = ""
        self.store.load_releases()
        job = self.store.upload_job
        self.assertEqual(
            first=(job.releases, job.latest_release, job.select_tag),
            second=(["A-mods", "b-mods"], "", "A-mods"),
        )


class RepoListTests(GitHubCase):
    def test_repos_keep_their_owner_and_details(self) -> None:
        self.hub.repos = ["me/mods", "friend/mods"]
        self.store.load_repos()
        job = self.store.upload_job
        self.assertEqual(first=job.repos, second=["friend/mods", "me/mods"])
        self.assertEqual(
            first=[(repo.name, repo.owner, repo.visibility) for repo in job.repo_details],
            second=[("mods", "friend", "public"), ("mods", "me", "public")],
        )
        self.assertEqual(first=(self.store.upload_repo, self.store.upload_tag), second=("me/mods", "reviewed"))

    def test_rows_that_are_not_repositories_are_dropped(self) -> None:
        rows = [{"full_name": "me/ok", "owner": "not a dict"}, {"full_name": "no slash"}, {"name": "x"}, "junk"]

        with mock.patch.object(target=uploader.api, attribute="pages", return_value=rows):
            repos = uploader.releases.list_repos()

        self.assertEqual(first=[(repo.full_name, repo.owner) for repo in repos], second=[("me/ok", "")])
