from typing import Dict, List, Optional

from pydantic import BaseModel, TypeAdapter

from .release_state import ReleaseRecord


# What this machine saved for a catalog id, in <catalog>.state.json. Older records may lack fields.
class DownloadRecord(BaseModel):
    file: str = ""
    sha256: str = ""
    version: str = ""
    downloaded_at: str = ""
    game_version: str = ""
    # Older records may name the folder instead of the file.
    folder: str = ""


# state.json of a release and where it came from; empty when unknown.
class ReleaseState(BaseModel):
    repo: str = ""
    tag: str = ""
    digest: str = ""
    mods: Dict[str, ReleaseRecord] = {}
    assets: Optional[List[str]] = None


# A <catalog>.state.json file: catalog id -> download record.
DOWNLOAD_RECORDS: TypeAdapter[Dict[str, DownloadRecord]] = TypeAdapter(type=Dict[str, DownloadRecord])
RELEASE_STATE: TypeAdapter[ReleaseState] = TypeAdapter(type=ReleaseState)


class EntryStatus(BaseModel):
    status: str
    remote: Optional[ReleaseRecord] = None
