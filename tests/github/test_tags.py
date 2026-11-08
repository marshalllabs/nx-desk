import unittest
from unittest import mock

from nx_desk import uploader
from tests.helpers import FakeGitHub


class DeleteTagTests(unittest.TestCase):
    def delete(self, hub: FakeGitHub, tag: str = "old") -> bool:
        with mock.patch.object(uploader.command, "gh", hub):
            return uploader.releases.delete_tag(repo="me/mods", tag=tag)

    def test_a_tag_is_removed(self) -> None:
        hub = FakeGitHub()
        hub.tags = {"old", "keep"}
        self.assertTrue(self.delete(hub=hub))
        self.assertEqual(hub.tags, {"keep"})

    def test_a_tag_that_is_already_gone_counts_as_removed(self) -> None:
        hub = FakeGitHub()
        hub.tags = set()
        self.assertTrue(self.delete(hub=hub))

    def test_a_refusal_is_reported_not_raised(self) -> None:
        hub = FakeGitHub()
        hub.tags = {"old"}
        hub.keep_tags = True
        self.assertFalse(self.delete(hub=hub))
        self.assertEqual(hub.tags, {"old"})

    def test_the_tag_name_goes_into_the_path_safely(self) -> None:
        seen: list[tuple[str, ...]] = []

        def gh(*args: str) -> str:
            seen.append(args)

            return ""

        with mock.patch.object(uploader.command, "gh", gh):
            uploader.releases.delete_tag(repo="me/mods", tag="a b/c")

        self.assertEqual(seen, [("api", "-X", "DELETE", "repos/me/mods/git/refs/tags/a%20b%2Fc")])
