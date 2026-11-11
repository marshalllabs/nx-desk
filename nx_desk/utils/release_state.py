import re
from datetime import UTC, datetime
from typing import Collection, List, Mapping, Optional

from ..schemas.release_state import ReleaseRecord

FOLDER_VERSION = re.compile(pattern=r" - \[[^\[\]]+\] - \[([^\[\]]+)\]$")
GAME_VERSION = re.compile(pattern=r"v?(\d+(?:\.\d+)*)", flags=re.IGNORECASE)


def find_record(records: Mapping[str, ReleaseRecord], entry_id: str, sha256: str) -> Optional[ReleaseRecord]:
    direct = records.get(entry_id)

    if direct is not None and (
        direct.failure is None
        or any((direct.sha256, direct.version, direct.game_version, direct.folder, direct.files, direct.uploaded_at))
    ):
        return direct

    digest = sha256.strip().lower()

    return next((record for record in records.values() if digest and record.sha256 == digest), None)


def saved_game_version(record: ReleaseRecord) -> str:
    if record.game_version:
        return record.game_version

    match = FOLDER_VERSION.search(string=record.folder)
    value = match.group(1) if match else ""

    return "" if value.casefold() == "miss" else value


def game_version_key(value: str) -> str:
    match = GAME_VERSION.search(string=value)

    return match.group(1) if match else ""


def content_matches(record: ReleaseRecord, sha256: str, version: str, game_version: str = "") -> bool:
    current_hash = sha256.strip().lower()

    if current_hash and record.sha256:
        return record.sha256 == current_hash

    if record.version and version.strip():
        if record.version != version.strip():
            return False

        old_game = game_version_key(value=saved_game_version(record=record))
        new_game = game_version_key(value=game_version)

        return not old_game or not new_game or old_game == new_game

    return False


def find_asset_name(name: str, names: Collection[str]) -> Optional[str]:
    return next((actual for actual in names if actual.casefold() == name.casefold()), None)


def assets_present(record: ReleaseRecord, names: Collection[str]) -> bool:
    available = {name.casefold() for name in names}

    return bool(record.files) and all(name.casefold() in available for name in record.files)


def build_record(
    sha256: str,
    version: str,
    game_version: str,
    folder: str,
    files: List[str],
    uploaded_at: Optional[str] = None,
) -> ReleaseRecord:
    return ReleaseRecord(
        sha256=sha256,
        version=version,
        game_version=game_version,
        folder=folder,
        files=files,
        uploaded_at=uploaded_at if uploaded_at is not None else datetime.now(tz=UTC).isoformat(timespec="seconds"),
    )


def refresh_metadata(
    record: ReleaseRecord,
    sha256: str,
    version: str,
    game_version: str,
    names: Collection[str],
) -> ReleaseRecord:
    data = record.model_dump()
    data["files"] = [find_asset_name(name=name, names=names) or name for name in record.files]

    # Only a matching original checksum proves catalog metadata describes the uploaded content.
    if sha256.strip() and record.sha256 == sha256.strip().lower():
        data["version"] = version.strip() or record.version
        data["game_version"] = game_version.strip() or record.game_version

    return ReleaseRecord.model_validate(obj=data)
