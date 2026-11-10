import threading
import time
from pathlib import Path
from typing import List
from unittest import mock

from nx_desk import names, zips
from nx_desk.schemas.catalog import Catalog, Mod
from nx_desk.schemas.download import Fetched, RepackTask
from nx_desk.schemas.release_state import ReleaseRecord
from nx_desk.schemas.state import ReleaseState
from tests.download.case import DownloadCase
from tests.helpers import TITLE, mod


# Two games in one Switch title, sold and modded as one file, like FINAL FANTASY X and X-2.
class TwinTests(DownloadCase):
    def twins(self) -> List[Mod]:
        self.store.titles = {TITLE: "Game X/X-2 HD"}
        self.store.items = self.store._named(items=[mod(id="x", name="Game X"), mod(id="x2", name="Game X-2")])

        return self.store.items

    def save(self, entry: Mod) -> Path:
        target = self.store.root / names.download_path(
            name=(entry.save_name or entry.name),
            version=entry.game_version,
            mod="VI",
        )
        target.parent.mkdir(parents=True)
        target.write_bytes(data=b"zip")
        self.store._commit(entry=entry, target=target)

        return target

    def test_one_file_keeps_each_name_and_saves_under_one(self) -> None:
        first, second = self.twins()
        self.assertEqual(first=(first.name, second.name), second=("Game X", "Game X-2"))
        self.assertEqual(first=(first.save_name, second.save_name), second=("Game X/X-2 HD", "Game X/X-2 HD"))
        self.assertEqual(first=(first.twins, second.twins), second=(["x2"], ["x"]))

    def test_one_title_in_two_files_saves_apart(self) -> None:
        self.store.titles = {TITLE: "Game"}
        old, new = self.store._named(
            items=[
                mod(id="old", name="Game Old Pack", sha256="a" * 64),
                mod(id="new", name="Game New Pack", sha256="b" * 64, url="https://example.com/b.zip"),
            ],
        )
        self.assertEqual(first=(old.name, old.save_name, old.twins), second=("Game Old Pack", "Game Old Pack", []))
        self.assertEqual(first=(new.name, new.save_name, new.twins), second=("Game New Pack", "Game New Pack", []))

    def test_a_lone_entry_takes_the_official_name(self) -> None:
        self.store.titles = {TITLE: "Real Game"}
        item = self.store._named(items=[mod(name="Catalog Name")])[0]
        self.assertEqual(first=(item.name, item.save_name, item.twins), second=("Real Game", "Real Game", []))

    def test_entries_without_a_hash_match_by_their_link(self) -> None:
        first, second = self.store._named(items=[mod(id="a", sha256=""), mod(id="b", sha256="")])
        self.assertEqual(first=(first.twins, second.twins), second=(["b"], ["a"]))

    def test_one_download_runs_for_both_rows(self) -> None:
        self.twins()
        self.store.enqueue(ids=["x", "x2"])
        self.assertEqual(first=list(self.store.jobs), second=["x"])
        rows = {item.id: item for item in self.store.snapshot().items}
        self.assertIsNotNone(obj=rows["x2"].job)
        self.store.cancel(entry_id="x2")
        self.assertEqual(first=self.store.jobs, second={})

    def test_a_saved_copy_counts_for_both(self) -> None:
        first, second = self.twins()
        self.save(entry=first)
        self.assertEqual(
            first=(self.store.status_of(entry=first), self.store.status_of(entry=second)),
            second=("ok", "ok"),
        )
        self.assertEqual(first=set(self.store.state), second={"x", "x2"})
        rows = {item.id: item for item in self.store.snapshot().items}
        self.assertEqual(first=rows["x2"].local_version, second=first.version)

    def test_a_record_saved_under_one_entry_counts_for_both(self) -> None:
        first, second = self.twins()
        self.save(entry=first)
        del self.store.state["x2"]
        self.assertEqual(first=self.store.status_of(entry=second), second="ok")

    def test_an_upload_recorded_under_one_entry_counts_for_both(self) -> None:
        _, second = self.twins()
        self.store.auto_delete = True
        self.store.auto_repo = "me/mods"
        self.store.catalog = Catalog(name="C", url="https://x.test/c.json", folder="c")
        self.store.release_state = ReleaseState(repo="me/mods", tag="c", mods={"x": ReleaseRecord(sha256="0" * 64)})
        self.assertEqual(first=self.store.status_of(entry=second), second="ok")

    def test_two_repacks_of_one_zip_take_turns(self) -> None:
        first, _ = self.twins()
        target = self.store.root / "Game" / "Game.zip"
        part = self.base / "game.part"
        part.write_bytes(data=b"part")
        repacked = threading.Event()

        def repack(target: Path, **_: object) -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data=b"zip")
            repacked.set()

        self.store.repack_queue.put(
            item=RepackTask(
                priority=1,
                order=0,
                entry=first,
                fetched=Fetched(wire=part),
                target=target,
                cancel=threading.Event(),
                started=time.monotonic(),
            ),
        )

        with mock.patch.object(target=zips, attribute="repack", side_effect=repack):
            with self.store.target_locks[target]:
                worker = threading.Thread(target=self.store._repack_next)
                worker.start()
                self.assertFalse(expr=repacked.wait(timeout=0.2))

            worker.join(timeout=5)

        self.assertTrue(expr=repacked.is_set())
