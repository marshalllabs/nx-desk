from unittest import mock

from tests.catalog.case import CatalogCase
from tests.helpers import job


class RefreshStatusTests(CatalogCase):
    def test_refresh_clears_failed_jobs_and_keeps_partial_downloads(self) -> None:
        self.add(name="First", url="https://example.com/first")
        self.store.jobs["one"] = job(phase="error", message="HTTP 500")
        self.store.parts.mkdir(exist_ok=True)
        part = self.store.parts / "one.part"
        part.write_bytes(data=b"partial download")

        with self.served(games=["one"]):
            self.store.check()

        row = self.store.snapshot().items[0]
        self.assertIsNone(row.job)
        self.assertEqual(row.status, "missing")
        self.assertEqual(part.read_bytes(), b"partial download")

    def test_refresh_keeps_active_jobs(self) -> None:
        self.add(name="First", url="https://example.com/first", games=["one", "two"])
        running = job(phase="downloading", done=10)
        self.store.jobs["one"] = running
        self.store.jobs["two"] = job(phase="error", message="HTTP 500")

        with self.served(games=["one", "two"]):
            self.store.check()

        self.assertEqual(self.store.jobs, {"one": running})

    def test_failed_refresh_does_not_restore_previous_download_errors(self) -> None:
        self.add(name="First", url="https://example.com/first")
        self.store.jobs["one"] = job(phase="error", message="old download error")

        with mock.patch("nx_desk.vault.catalogs.fetch_catalog", side_effect=OSError("catalog unavailable")):
            self.store.check()

        self.assertIsNone(self.store.snapshot().items[0].job)
        self.assertEqual(self.store.check_error, "catalog unavailable")

    def test_switching_catalog_clears_errors_for_shared_mod_ids(self) -> None:
        first = self.add(name="First", url="https://example.com/first")
        self.add(name="Second", url="https://example.com/second")
        self.store.jobs["one"] = job(phase="error", message="HTTP 500")
        self.store.select_catalog(folder=first.folder)

        self.assertIsNone(self.store.snapshot().items[0].job)
