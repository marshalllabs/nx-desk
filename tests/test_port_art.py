import threading
import time
import unittest
from pathlib import Path
from typing import List, Optional, Tuple

from nx_desk.config import ART_WORKERS
from nx_desk.schemas.artwork import ArtFiles, ArtSources, ArtSubject
from nx_desk.schemas.catalog import ArtKind
from nx_desk.schemas.port import Port
from nx_desk.vault.art_queue import ArtQueue

EMPTY_ART = ArtSources()


# Answers like the vault does, holding each lookup until the test lets it go.
class FakeVault:
    def __init__(self, key: bool = True, answer: Optional[ArtSources] = EMPTY_ART) -> None:
        self.key = key
        self.answer = answer
        self.art_version = 0
        self.ports_art_dir = Path("art")
        self.release = threading.Event()
        self.started: List[str] = []
        self.fetched: List[Tuple[str, str]] = []

    def has_art_key(self) -> bool:
        return self.key

    def steamgrid_art(self, item: ArtSubject) -> Optional[ArtSources]:
        self.started.append(item.id)
        self.release.wait(timeout=5)

        return self.answer

    def fetch_art(self, item: ArtSubject, kind: ArtKind, url: str, art_dir: Path) -> Optional[Path]:
        self.fetched.append((kind, url))

        return Path(f"{item.id.replace('/', '-')}-{kind}") if url else None


def ports(count: int) -> List[Port]:
    return [Port(id=f"o/game{number}", name=f"Game {number}", platform="PC") for number in range(count)]


def wait_for(condition: object, seconds: float = 3) -> bool:
    end = time.time() + seconds

    while time.time() < end:
        if callable(condition) and condition():
            return True

        time.sleep(0.01)

    return False


class PortArtTests(unittest.TestCase):
    def make(self, key: bool = True, answer: Optional[ArtSources] = EMPTY_ART) -> Tuple[ArtQueue, FakeVault]:
        fake = FakeVault(key=key, answer=answer)

        return ArtQueue(vault=fake), fake

    def test_a_few_entries_are_asked_at_a_time_in_order(self) -> None:
        art, fake = self.make()
        art.want(items=ports(count=10))
        self.assertTrue(expr=wait_for(condition=lambda: len(fake.started) == ART_WORKERS))
        self.assertEqual(first=sorted(fake.started), second=[f"o/game{number}" for number in range(ART_WORKERS)])
        fake.release.set()
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertEqual(first=len(fake.started), second=10)
        self.assertEqual(first=len(art.files), second=10)

    def test_a_new_list_drops_the_entries_still_waiting(self) -> None:
        art, fake = self.make()
        art.want(items=ports(count=10))
        self.assertTrue(expr=wait_for(condition=lambda: len(fake.started) == ART_WORKERS))
        art.want(items=ports(count=10)[8:])
        fake.release.set()
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertEqual(
            first=sorted(fake.started),
            second=sorted([f"o/game{n}" for n in range(ART_WORKERS)] + ["o/game8", "o/game9"]),
        )

    def test_an_entry_is_not_asked_twice(self) -> None:
        art, fake = self.make()
        fake.release.set()
        art.want(items=ports(count=3))
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        art.want(items=ports(count=3))
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertEqual(first=len(fake.started), second=3)

    def test_without_a_key_nothing_is_asked(self) -> None:
        art, fake = self.make(key=False)
        art.want(items=ports(count=3))
        self.assertEqual(first=(fake.started, art.workers), second=([], 0))
        self.assertTrue(expr=art.needs_key())

    def test_an_unanswered_entry_is_asked_again_later(self) -> None:
        art, fake = self.make(answer=None)
        fake.release.set()
        art.want(items=ports(count=1))
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        art.want(items=ports(count=1))
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertEqual(first=len(fake.started), second=2)
        self.assertEqual(first=art.files, second={})

    def test_a_new_key_forgets_what_was_found(self) -> None:
        art, fake = self.make()
        fake.release.set()
        art.want(items=ports(count=2))
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        fake.art_version = 1
        art.check_key()
        self.assertEqual(first=(art.files, art.asked), second=({}, set()))

    def test_an_entry_steamgriddb_lacks_gets_the_github_card(self) -> None:
        art, fake = self.make(answer=ArtSources())
        fake.release.set()
        port = Port(id="o/game", name="Game", platform="PC", url="https://github.com/O/Game")
        art.want(items=[port])
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertIn(member=("background", "https://opengraph.githubassets.com/1/O/Game"), container=fake.fetched)
        self.assertIsNotNone(obj=art.files[port.id].background)

    def test_an_entry_with_art_gets_no_card_and_another_host_none_at_all(self) -> None:
        art, fake = self.make(answer=ArtSources(cover="https://cdn2.steamgriddb.com/grid/c.png"))
        fake.release.set()
        art.want(items=[Port(id="o/game", name="Game", platform="PC", url="https://github.com/o/game")])
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertEqual(first=[url for _, url in fake.fetched if "githubassets" in url], second=[])
        other, fake = self.make(answer=ArtSources())
        fake.release.set()
        other.want(items=[Port(id="g/game", name="Game", platform="PC", url="https://gitlab.com/g/game")])
        self.assertTrue(expr=wait_for(condition=lambda: other.workers == 0))
        self.assertEqual(first=other.files["g/game"], second=ArtFiles())

    def test_an_entry_with_no_art_is_settled_and_one_still_waiting_is_not(self) -> None:
        art, fake = self.make(answer=ArtSources())
        port = ports(count=1)[0]
        self.assertFalse(expr=art.settled(item=port))
        art.want(items=[port])
        self.assertTrue(expr=wait_for(condition=lambda: len(fake.started) == 1))
        self.assertFalse(expr=art.settled(item=port))
        fake.release.set()
        self.assertTrue(expr=wait_for(condition=lambda: art.workers == 0))
        self.assertTrue(expr=art.settled(item=port))
        keyless, _ = self.make(key=False)
        self.assertTrue(expr=keyless.settled(item=port))
