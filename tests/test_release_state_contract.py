import unittest
from pathlib import Path
from typing import List

from pydantic import BaseModel, ValidationError

from nx_desk.schemas.release_state import ReleaseDocument, ReleaseRecord
from nx_desk.utils.release_state import (
    assets_present,
    build_record,
    content_matches,
    find_record,
    refresh_metadata,
    saved_game_version,
)


class ContractCase(BaseModel):
    name: str
    record: ReleaseRecord
    sha256: str
    version: str
    game_version: str
    expected: bool
    expected_game_version: str
    names: List[str]
    expected_assets: bool


class ContractFixture(BaseModel):
    cases: List[ContractCase]


class ReleaseStateContractTests(unittest.TestCase):
    def test_common_legacy_and_comparison_vectors(self) -> None:
        path = Path(__file__).parent / "fixtures" / "release_state_contract.json"
        fixture = ContractFixture.model_validate_json(json_data=path.read_text(encoding="utf-8"))

        for case in fixture.cases:
            with self.subTest(name=case.name):
                self.assertEqual(
                    first=content_matches(
                        record=case.record,
                        sha256=case.sha256,
                        version=case.version,
                        game_version=case.game_version,
                    ),
                    second=case.expected,
                )
                self.assertEqual(first=saved_game_version(record=case.record), second=case.expected_game_version)
                self.assertEqual(
                    first=assets_present(record=case.record, names=case.names),
                    second=case.expected_assets,
                )

    def test_both_writers_emit_the_same_complete_record(self) -> None:
        record = build_record(
            sha256=" AAAAAA ",
            version=" v1 ",
            game_version=" Update 1.0.2 ",
            folder=" Game - [VI] - [1.0.2] ",
            files=["b.zip.002", "b.zip.001", "b.zip.001"],
            uploaded_at="2026-01-01T00:00:00+00:00",
        )
        expected = {
            "sha256": "aaaaaa",
            "version": "v1",
            "game_version": "Update 1.0.2",
            "folder": "Game - [VI] - [1.0.2]",
            "files": ["b.zip.001", "b.zip.002"],
            "uploaded_at": "2026-01-01T00:00:00+00:00",
        }
        self.assertEqual(first=record.model_dump(), second=expected)
        document = ReleaseDocument(catalog="https://example.com/catalog", mods={"synthetic": record})
        parsed = ReleaseDocument.model_validate_json(json_data=document.model_dump_json())
        self.assertEqual(first=parsed.mods["synthetic"].model_dump(), second=expected)
        self.assertEqual(first=parsed.version, second=1)

    def test_legacy_missing_and_null_fields_have_the_same_defaults(self) -> None:
        record = ReleaseRecord.model_validate(
            obj={"sha256": None, "game_version": None, "files": [None, "b.zip", "a.zip", "b.zip"]},
        )
        self.assertEqual(first=record.sha256, second="")
        self.assertEqual(first=record.game_version, second="")
        self.assertEqual(first=record.files, second=["a.zip", "b.zip"])
        self.assertEqual(first=ReleaseRecord.model_validate(obj={"files": None}).files, second=[])

    def test_malformed_state_is_never_treated_as_empty(self) -> None:
        for text in ('{"mods":null}', '{"mods":[]}', '{"mods":{"synthetic":false}}', '{"version":2,"mods":{}}'):
            with self.subTest(text=text), self.assertRaises(expected_exception=ValidationError):
                ReleaseDocument.model_validate_json(json_data=text)

    def test_metadata_refresh_keeps_asset_paths_timestamp_and_unknown_fields(self) -> None:
        record = ReleaseRecord.model_validate(
            obj={
                "sha256": "a" * 64,
                "version": "v1",
                "folder": "Legacy Name",
                "files": ["Existing.zip"],
                "uploaded_at": "2026-01-01T00:00:00+00:00",
                "metadata": {"keep": True},
            },
        )
        refreshed = refresh_metadata(
            record=record,
            sha256="a" * 64,
            version="v2",
            game_version="Update 1.0.2",
            names=["existing.zip"],
        )
        self.assertEqual(first=refreshed.version, second="v2")
        self.assertEqual(first=refreshed.game_version, second="Update 1.0.2")
        self.assertEqual(first=refreshed.folder, second=record.folder)
        self.assertEqual(first=refreshed.uploaded_at, second=record.uploaded_at)
        self.assertEqual(first=refreshed.files, second=["existing.zip"])
        self.assertEqual(first=refreshed.model_dump()["metadata"], second={"keep": True})
        self.assertEqual(first=record.game_version, second="")

    def test_version_fallback_does_not_invent_source_hash(self) -> None:
        record = ReleaseRecord(version="v1", files=["existing.zip"])
        refreshed = refresh_metadata(
            record=record,
            sha256="a" * 64,
            version="v1",
            game_version="1.0.2",
            names=["existing.zip"],
        )
        self.assertEqual(first=refreshed.sha256, second="")
        self.assertEqual(first=refreshed.game_version, second="")

    def test_shared_file_can_be_found_by_original_hash_for_another_id(self) -> None:
        record = ReleaseRecord(sha256="a" * 64, files=["existing.zip"])
        records = {"first": record}
        self.assertEqual(first=find_record(records=records, entry_id="second", sha256="a" * 64), second=record)
        self.assertIsNone(obj=find_record(records=records, entry_id="second", sha256=""))
        self.assertIsNone(obj=find_record(records=records, entry_id="second", sha256="b" * 64))
        newer = ReleaseRecord(sha256="b" * 64)
        records["second"] = newer
        self.assertEqual(first=find_record(records=records, entry_id="second", sha256="a" * 64), second=newer)

    def test_catalog_metadata_does_not_depend_on_a_gist_revision(self) -> None:
        base = "https://gist.githubusercontent.com/example/synthetic/raw/"
        document = ReleaseDocument(catalog=f"{base}{'a' * 40}/catalog.json")
        self.assertEqual(first=document.catalog, second=base + "catalog.json")
        document.catalog = f"{base}{'b' * 40}/catalog.json"
        self.assertEqual(first=document.catalog, second=base + "catalog.json")
