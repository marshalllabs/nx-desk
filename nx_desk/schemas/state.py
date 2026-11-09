from typing import Dict, List, Optional

from pydantic import BaseModel, TypeAdapter, field_validator


# What this machine saved for a catalog id, in <catalog>.state.json. Older records may lack fields.
class DownloadRecord(BaseModel):
    file: str = ""
    sha256: str = ""
    version: str = ""
    downloaded_at: str = ""
    game_version: str = ""
    # Older records may name the folder instead of the file.
    folder: str = ""


# One mod in state.json on a release. Read from GitHub, so every field may be missing.
class ReleaseRecord(BaseModel):
    sha256: str = ""
    version: str = ""
    game_version: str = ""
    folder: str = ""
    files: List[str] = []
    uploaded_at: str = ""


# state.json of a release and where it came from; empty when unknown.
class ReleaseState(BaseModel):
    repo: str = ""
    tag: str = ""
    digest: str = ""
    mods: Dict[str, ReleaseRecord] = {}


# A <catalog>.state.json file: catalog id -> download record.
DOWNLOAD_RECORDS: TypeAdapter[Dict[str, DownloadRecord]] = TypeAdapter(type=Dict[str, DownloadRecord])
RELEASE_STATE: TypeAdapter[ReleaseState] = TypeAdapter(type=ReleaseState)


class EntryStatus(BaseModel):
    status: str
    remote: Optional[ReleaseRecord] = None


class RemoteRecord(ReleaseRecord):
    @field_validator("sha256", "version", "game_version", "folder", "uploaded_at", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    @field_validator("files", mode="before")
    @classmethod
    def _files(cls, value: object) -> List[str]:
        return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


class ReleaseDocument(BaseModel):
    catalog: str = ""
    mods: Dict[str, RemoteRecord] = {}

    @field_validator("catalog", mode="before")
    @classmethod
    def _catalog(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    @field_validator("mods", mode="before")
    @classmethod
    def _mods(cls, value: object) -> object:
        if not isinstance(value, dict):
            return {}

        return {key: record for key, record in value.items() if isinstance(key, str) and isinstance(record, dict)}
