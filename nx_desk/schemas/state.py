from pydantic import BaseModel, TypeAdapter


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
    files: list[str] = []
    uploaded_at: str = ""


# state.json of a release and where it came from; empty when unknown.
class ReleaseState(BaseModel):
    repo: str = ""
    tag: str = ""
    digest: str = ""
    mods: dict[str, ReleaseRecord] = {}


# A <catalog>.state.json file: catalog id -> download record.
DOWNLOAD_RECORDS: TypeAdapter[dict[str, DownloadRecord]] = TypeAdapter(dict[str, DownloadRecord])
RELEASE_STATE: TypeAdapter[ReleaseState] = TypeAdapter(ReleaseState)
