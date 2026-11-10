import tempfile
import threading
import unittest
from pathlib import Path
from typing import List
from unittest import mock

from nx_desk import credentials, uploader, vault


class GitHubAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.base = Path(folder.name)
        self.store = vault.Vault(base=self.base)

    def test_token_is_stored_only_in_keyring_and_survives_a_new_vault(self) -> None:
        with (
            mock.patch.object(target=credentials, attribute="keyring_set", return_value=True) as save,
            mock.patch.object(target=credentials, attribute="keyring_get", return_value="synthetic-pat"),
        ):
            self.store.set_github_token(token="synthetic-pat")
            again = vault.Vault(base=self.base)
            self.assertTrue(expr=again.github_token_saved)
            self.assertEqual(first=again._github_token(), second="synthetic-pat")

        self.assertEqual(first=save.call_args.kwargs["value"], second="synthetic-pat")
        self.assertNotIn(member="synthetic-pat", container=self.store.registry_path.read_text())
        self.assertFalse(expr=(self.store.catalogs_dir / credentials.KEY_FILE).exists())

    def test_missing_keyring_rejects_save_without_file_fallback(self) -> None:
        with (
            mock.patch.object(target=credentials, attribute="keyring_set", return_value=False),
            self.assertRaises(expected_exception=ValueError),
        ):
            self.store.set_github_token(token="synthetic-pat")

        self.assertFalse(expr=self.store.github_token_saved)
        self.assertIsNone(obj=self.store.github_secret)
        self.assertFalse(expr=self.store.registry_path.exists())

    def test_remove_forgets_cached_and_persisted_token(self) -> None:
        with mock.patch.object(target=credentials, attribute="keyring_set", return_value=True):
            self.store.set_github_token(token="synthetic-pat")

        with mock.patch.object(target=credentials, attribute="keyring_delete", return_value=True) as remove:
            self.store.set_github_token(token="")

        remove.assert_called_once()
        self.assertEqual(first=self.store._github_token(), second="")
        self.assertFalse(expr=self.store.github_token_saved)
        self.assertFalse(expr=self.store.github_ready)

    def test_failed_remove_preserves_saved_state(self) -> None:
        with mock.patch.object(target=credentials, attribute="keyring_set", return_value=True):
            self.store.set_github_token(token="synthetic-pat")

        with (
            mock.patch.object(target=credentials, attribute="keyring_delete", return_value=False),
            self.assertRaises(expected_exception=ValueError),
        ):
            self.store.set_github_token(token="")

        self.assertTrue(expr=self.store.github_token_saved)
        self.assertEqual(first=self.store._github_token(), second="synthetic-pat")

    def test_busy_github_job_prevents_token_changes(self) -> None:
        with (
            self.store.github_lock,
            mock.patch.object(target=credentials, attribute="keyring_set") as save,
            self.assertRaises(expected_exception=ValueError),
        ):
            self.store.set_github_token(token="synthetic-pat")

        save.assert_not_called()

    def test_missing_token_explains_how_to_configure_it(self) -> None:
        self.store.github_secret = ""
        self.store._bind_github()

        with self.assertRaises(expected_exception=uploader.command.GitHubError) as caught:
            uploader.command.token()

        self.assertIn(member="Settings > GitHub", container=str(caught.exception))

    def test_multiple_vaults_do_not_share_tokens_across_threads(self) -> None:
        other = vault.Vault(base=self.base / "other")
        self.store.github_secret = "first-synthetic"
        other.github_secret = "second-synthetic"
        barrier = threading.Barrier(parties=2)
        seen: List[str] = []

        def read(store: vault.Vault) -> None:
            store._bind_github()
            barrier.wait(timeout=2)
            seen.append(uploader.command.token())

        threads = [threading.Thread(target=read, kwargs={"store": store}) for store in (self.store, other)]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join(timeout=3)

        self.assertEqual(first=set(seen), second={"first-synthetic", "second-synthetic"})

    def test_unlocking_keyring_allows_a_later_attempt(self) -> None:
        self.store.github_token_saved = True

        with mock.patch.object(target=credentials, attribute="keyring_get", side_effect=["", "synthetic-pat"]):
            with self.assertRaises(expected_exception=uploader.command.GitHubError):
                self.store._github_token()

            self.assertEqual(first=self.store._github_token(), second="synthetic-pat")
