import unittest
from typing import List, Tuple
from unittest import mock

from nx_desk import uploader
from tests.helpers import FakeGitHub


class DeleteTagTests(unittest.TestCase):
    def delete(self, hub: FakeGitHub, tag: str = "old") -> bool:
        with mock.patch.object(target=uploader.command, attribute="gh", new=hub):
            return uploader.releases.delete_tag(repo="me/mods", tag=tag)

    def test_a_tag_is_removed(self) -> None:
        hub = FakeGitHub()
        hub.tags = {"old", "keep"}
        self.assertTrue(expr=self.delete(hub=hub))
        self.assertEqual(first=hub.tags, second={"keep"})

    def test_a_tag_that_is_already_gone_counts_as_removed(self) -> None:
        hub = FakeGitHub()
        hub.tags = set()
        self.assertTrue(expr=self.delete(hub=hub))

    def test_a_refusal_is_reported_not_raised(self) -> None:
        hub = FakeGitHub()
        hub.tags = {"old"}
        hub.keep_tags = True
        self.assertFalse(expr=self.delete(hub=hub))
        self.assertEqual(first=hub.tags, second={"old"})

    def test_the_tag_name_goes_into_the_path_safely(self) -> None:
        seen: List[Tuple[str, ...]] = []

        def gh(*args: str) -> str:
            seen.append(args)

            return ""

        with mock.patch.object(target=uploader.command, attribute="gh", new=gh):
            uploader.releases.delete_tag(repo="me/mods", tag="a b/c")

        self.assertEqual(first=seen, second=[("api", "-X", "DELETE", "repos/me/mods/git/refs/tags/a%20b%2Fc")])
