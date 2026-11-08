import threading
import time
import unittest
from pathlib import Path
from typing import cast

from nx_desk.config import ART_WORKERS
from nx_desk.schemas.port import Port
from nx_desk.vault import Vault
from nx_desk.vault.art_queue import ArtQueue


# Answers like the vault does, holding each lookup until the test lets it go.
class FakeVault:
    def __init__(self, key: bool = True, answer: tuple[str, str] | None = ("", "")) -> None:
        self.key = key
        self.answer = answer
        self.art_version = 0
        self.ports_art_dir = Path("art")
        self.release = threading.Event()
        self.started: list[str] = []
        self.fetched: list[tuple[str, str]] = []

    def has_art_key(self) -> bool:
        return self.key

    def steamgrid_art(self, item: Port) -> tuple[str, str] | None:
        self.started.append(item.id)
        self.release.wait(timeout=5)

        return self.answer

    def fetch_art(self, item: Port, kind: str, url: str, art_dir: Path) -> Path | None:
        self.fetched.append((kind, url))

        return Path(f"{item.id.replace('/', '-')}-{kind}") if url else None


def ports(count: int) -> list[Port]:
    return [Port(id=f"o/game{number}", name=f"Game {number}", platform="PC") for number in range(count)]


def wait_for(condition: object, seconds: float = 3) -> bool:
    end = time.time() + seconds

    while time.time() < end:
        if callable(condition) and condition():
            return True

        time.sleep(0.01)

    return False


class PortArtTests(unittest.TestCase):
    def make(self, **options: object) -> tuple[ArtQueue, FakeVault]:
        fake = FakeVault(**options)  # type: ignore[arg-type]

        return ArtQueue(vault=cast(Vault, fake)), fake

    def test_a_few_entries_are_asked_at_a_time_in_order(self) -> None:
        art, fake = self.make()
        art.want(ports=ports(count=10))
        self.assertTrue(wait_for(lambda: len(fake.started) == ART_WORKERS))
        self.assertEqual(sorted(fake.started), [f"o/game{number}" for number in range(ART_WORKERS)])
        fake.release.set()
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertEqual(len(fake.started), 10)
        self.assertEqual(len(art.files), 10)

    def test_a_new_list_drops_the_entries_still_waiting(self) -> None:
        art, fake = self.make()
        art.want(ports=ports(count=10))
        self.assertTrue(wait_for(lambda: len(fake.started) == ART_WORKERS))
        art.want(ports=ports(count=10)[8:])
        fake.release.set()
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertEqual(
            sorted(fake.started),
            sorted([f"o/game{n}" for n in range(ART_WORKERS)] + ["o/game8", "o/game9"]),
        )

    def test_an_entry_is_not_asked_twice(self) -> None:
        art, fake = self.make()
        fake.release.set()
        art.want(ports=ports(count=3))
        self.assertTrue(wait_for(lambda: art.workers == 0))
        art.want(ports=ports(count=3))
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertEqual(len(fake.started), 3)

    def test_without_a_key_nothing_is_asked(self) -> None:
        art, fake = self.make(key=False)
        art.want(ports=ports(count=3))
        self.assertEqual((fake.started, art.workers), ([], 0))
        self.assertTrue(art.needs_key())

    def test_an_unanswered_entry_is_asked_again_later(self) -> None:
        art, fake = self.make(answer=None)
        fake.release.set()
        art.want(ports=ports(count=1))
        self.assertTrue(wait_for(lambda: art.workers == 0))
        art.want(ports=ports(count=1))
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertEqual(len(fake.started), 2)
        self.assertEqual(art.files, {})

    def test_a_new_key_forgets_what_was_found(self) -> None:
        art, fake = self.make()
        fake.release.set()
        art.want(ports=ports(count=2))
        self.assertTrue(wait_for(lambda: art.workers == 0))
        fake.art_version = 1
        art.check_key()
        self.assertEqual((art.files, art.asked), ({}, set()))

    def test_an_entry_steamgriddb_lacks_gets_the_github_card(self) -> None:
        art, fake = self.make(answer=("", ""))
        fake.release.set()
        port = Port(id="o/game", name="Game", platform="PC", url="https://github.com/O/Game")
        art.want(ports=[port])
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertIn(("background", "https://opengraph.githubassets.com/1/O/Game"), fake.fetched)
        self.assertIsNotNone(art.files[port.id][1])

    def test_an_entry_with_art_gets_no_card_and_another_host_none_at_all(self) -> None:
        art, fake = self.make(answer=("https://cdn2.steamgriddb.com/grid/c.png", ""))
        fake.release.set()
        art.want(ports=[Port(id="o/game", name="Game", platform="PC", url="https://github.com/o/game")])
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertEqual([url for _, url in fake.fetched if "githubassets" in url], [])
        other, fake = self.make(answer=("", ""))
        fake.release.set()
        other.want(ports=[Port(id="g/game", name="Game", platform="PC", url="https://gitlab.com/g/game")])
        self.assertTrue(wait_for(lambda: other.workers == 0))
        self.assertEqual(other.files["g/game"], (None, None))

    def test_an_entry_with_no_art_is_settled_and_one_still_waiting_is_not(self) -> None:
        art, fake = self.make(answer=("", ""))
        port = ports(count=1)[0]
        self.assertFalse(art.settled(port=port))
        art.want(ports=[port])
        self.assertTrue(wait_for(lambda: len(fake.started) == 1))
        self.assertFalse(art.settled(port=port))
        fake.release.set()
        self.assertTrue(wait_for(lambda: art.workers == 0))
        self.assertTrue(art.settled(port=port))
        keyless, _ = self.make(key=False)
        self.assertTrue(keyless.settled(port=port))
