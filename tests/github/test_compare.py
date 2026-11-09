from typing import Dict, List

from nx_desk import uploader
from nx_desk.schemas.github import CompareRow
from nx_desk.ui.rows import compare_status
from tests.github.case import GitHubCase
from tests.helpers import asset


def states(rows: List[CompareRow]) -> Dict[str, str]:
    return {row.key: row.state for row in rows}


class CompareTests(GitHubCase):
    def test_files_match_by_name_and_games_by_label(self) -> None:
        left = [
            asset(name="Hades-VI-1-0.zip", label="Hades - [VI] - [1.0]"),
            asset(name="Celeste-VI-2-0.zip", label="Celeste - [VI] - [2.0]"),
            asset(name="Owl-VI-1-0.zip", label="Owl - [VI] - [1.0]"),
        ]
        right = [
            asset(name="Hades-VI-1-0.zip", label="Hades - [VI] - [1.0]"),
            asset(name="Celeste-EN-2-1.zip", label="Celeste - [EN] - [2.1]"),
            asset(name="Tunic-VI-1-0.zip", label="Tunic - [VI] - [1.0]"),
        ]
        comparison = uploader.compare.compare_releases(left=left, right=right)
        first = comparison.left
        second = comparison.right
        self.assertEqual(
            first=states(rows=first),
            second={"Hades-VI-1-0.zip": "same", "Celeste-VI-2-0.zip": "differs", "Owl-VI-1-0.zip": "only"},
        )
        self.assertEqual(
            first=states(rows=second),
            second={"Hades-VI-1-0.zip": "same", "Celeste-EN-2-1.zip": "differs", "Tunic-VI-1-0.zip": "only"},
        )
        differs = next(row for row in first if row.state == "differs")
        self.assertEqual(first=compare_status(row=differs), second="Other version: [EN] - [2.1]")

    def test_parts_of_one_file_are_one_row(self) -> None:
        left = [
            asset(name="Big-VI-1-0.zip.001", size=3, label="Big - [VI] - [1.0]"),
            asset(name="Big-VI-1-0.zip.002", size=2, label="Big - [VI] - [1.0]"),
        ]
        comparison = uploader.compare.compare_releases(left=left, right=[asset(name="Big-VI-1-0.zip")])
        first = comparison.left
        second = comparison.right
        self.assertEqual(
            first=[(row.key, row.size, row.state) for row in first],
            second=[("Big-VI-1-0.zip", 5, "same")],
        )
        self.assertEqual(first=second[0].files, second=["Big-VI-1-0.zip"])

    def test_a_file_without_a_label_only_matches_by_name(self) -> None:
        comparison = uploader.compare.compare_releases(
            left=[asset(name="Old-VI-1-0.zip")],
            right=[asset(name="Old-VI-2-0.zip", label="Old - [VI] - [2.0]")],
        )
        first = comparison.left
        self.assertEqual(first=states(rows=first), second={"Old-VI-1-0.zip": "only"})

    def test_split_files_count_once_in_the_messages(self) -> None:
        for name in ("Big-VI-1-0.zip.001", "Big-VI-1-0.zip.002", "Hades-VI-1-0.zip"):
            self.hub.add(name=name, digest="sha256:x")

        self.store.load_compare(tag="other")
        self.assertEqual(first=self.store.upload_job.message, second="Comparing with release other, which has 2 games.")
        self.assertEqual(first=uploader.parts.games_text(assets=[asset(name="a.zip")]), second="1 game")

    def test_loading_and_closing_a_second_release(self) -> None:
        self.hub.add(name="Hades-VI-1-0.zip", digest="sha256:x")
        self.hub.add(name="state.json", digest="sha256:y")
        self.store.load_compare(tag="other")
        job = self.store.upload_job
        self.assertEqual(
            first=(job.compare_tag, [item.name for item in job.compare_assets]),
            second=("other", ["Hades-VI-1-0.zip"]),
        )
        self.store.close_compare()
        self.assertEqual(
            first=(self.store.upload_job.compare_tag, self.store.upload_job.compare_assets),
            second=("", []),
        )
