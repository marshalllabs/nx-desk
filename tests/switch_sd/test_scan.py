import hashlib
import threading

from nx_desk.schemas.switch_sd import MountedVolume, SDContentIdentity, SDManifest, SDPackageInfo
from nx_desk.switch_sd import detect, paths, scan
from tests.switch_sd.case import OTHER, TITLE, SDCase


class DetectionTests(SDCase):
    def test_normal_cards_and_nintendo_only_cards_are_ignored(self) -> None:
        normal = self.base / "ordinary"
        (normal / "Nintendo").mkdir(parents=True)
        cards = detect.discover(volumes=[self.volume, MountedVolume(root=normal, filesystem="exfat")])
        self.assertEqual(first=[card.root for card in cards], second=[self.root])

    def test_wrong_filesystems_and_symlinked_markers_are_ignored(self) -> None:
        self.assertIsNone(obj=detect.detect(volume=self.volume.model_copy(update={"filesystem": "ext4"})))
        marker = self.root / "atmosphere" / "package3"
        marker.unlink()
        target = self.base / "marker"
        target.write_bytes(data=b"synthetic")
        marker.symlink_to(target=target)
        self.assertIsNone(obj=detect.detect(volume=self.volume))

    def test_hekate_layout_needs_atmosphere_contents(self) -> None:
        (self.root / "atmosphere" / "package3").unlink()
        (self.root / "bootloader").mkdir()
        (self.root / "bootloader" / "hekate_ipl.ini").write_text(data="[synthetic]")
        self.assertIsNone(obj=detect.detect(volume=self.volume))
        (self.root / "atmosphere" / "contents").mkdir()
        self.assertIsNotNone(obj=detect.detect(volume=self.volume))

    def test_read_only_card_is_detected_and_marked(self) -> None:
        card = detect.detect(volume=self.volume.model_copy(update={"read_only": True}))
        assert card is not None
        self.assertTrue(expr=card.read_only)

    def test_marker_change_invalidates_the_card_reference(self) -> None:
        (self.root / "atmosphere" / "package3").write_bytes(data=b"changed")

        with self.assertRaises(expected_exception=ValueError):
            detect.require(card=self.card)


class ScanTests(SDCase):
    def test_system_prefix_does_not_guess_category(self) -> None:
        self.put(relative=f"{TITLE}/exefs.nsp")
        row = scan.scan(card=self.card, names={}, cancel=self.cancel)[0]
        self.assertEqual(first=row.category, second="")
        self.assertEqual(first=row.kinds, second=["exefs.nsp"])

    def test_types_title_mapping_and_unknown_versions(self) -> None:
        self.put(relative=f"{TITLE}/romfs/a", data=b"abc")
        self.put(relative=f"{TITLE}/cheats/build.txt", data=b"cheat")
        self.put(relative=f"{OTHER}/exefs/main", data=b"binary")
        rows = scan.scan(
            card=self.card,
            names={TITLE: SDContentIdentity(name="Known game", category="Game")},
            cancel=self.cancel,
        )
        first = next(row for row in rows if row.title_id == TITLE)
        self.assertEqual(
            first=(first.name, first.kinds, first.files, first.size),
            second=("Known game", ["cheats", "romfs"], 2, 8),
        )
        self.assertEqual(first=(first.mod_version, first.target_game), second=("", ""))

    def test_legacy_metadata_is_verified_without_changing_card_files(self) -> None:
        self.put(relative=f"{TITLE}/romfs/a", data=b"synthetic")
        metadata = SDManifest(
            packages=[SDPackageInfo(id="old", name="Synthetic game", mod_version="v1", game_version="1.0")],
            files={"romfs/a": hashlib.sha256(string=b"synthetic").hexdigest()},
        )
        self.put(relative=f"{TITLE}/.nx-desk.json", data=metadata.model_dump_json().encode(encoding="utf-8"))
        before = {path: path.read_bytes() for path in self.root.rglob(pattern="*") if path.is_file()}
        row = scan.scan(card=self.card, names={}, cancel=self.cancel)[0]
        self.assertEqual(first=(row.status, row.mod_version, row.target_game), second=("Verified copy", "v1", "1.0"))
        after = {path: path.read_bytes() for path in self.root.rglob(pattern="*") if path.is_file()}
        self.assertEqual(first=after, second=before)

    def test_symlinks_do_not_escape_the_card(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "data").write_bytes(data=b"synthetic")
        title = self.root / "atmosphere" / "contents" / TITLE
        title.parent.mkdir()
        title.symlink_to(target=outside, target_is_directory=True)
        rows = scan.scan(card=self.card, names={}, cancel=self.cancel)
        self.assertEqual(first=rows[0].status, second="Unreadable / unsafe")

    def test_cancel_stops_scanning(self) -> None:
        self.put(relative=f"{TITLE}/romfs/a")
        event = threading.Event()
        event.set()

        from nx_desk.zips import Cancelled

        with self.assertRaises(expected_exception=Cancelled):
            scan.scan(card=self.card, names={}, cancel=event)

    def test_protected_names_are_rejected_without_opening_files(self) -> None:
        for name in ("romfs/.env", "romfs/prod.keys", "../outside", "romfs/name:stream", "/absolute"):
            with self.subTest(name=name), self.assertRaises(expected_exception=ValueError):
                paths.relative_parts(name=name)
