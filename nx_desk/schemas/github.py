import threading
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict

from .common import LogEntry


# A repository the signed-in user can reach, as the repository picker lists it.
class Repo(BaseModel):
    full_name: str
    name: str = ""
    owner: str = ""
    visibility: str = ""
    description: str = ""
    updated_at: str = ""


# A release file as the GitHub API returns it, trimmed to the fields used here.
class Asset(BaseModel):
    id: int
    name: str
    size: int = 0
    digest: Optional[str] = None
    label: Optional[str] = None
    updated_at: str = ""


class FolderRef(BaseModel):
    name: str
    path: Path
    size: int


# A mod folder in the source of the GitHub tab; each one is one upload.
class Folder(FolderRef):
    # Updated field by field while it runs, so each change is checked too.
    model_config = ConfigDict(validate_assignment=True)

    status: str
    message: str
    progress: str
    # The release file name its zip gets.
    asset: str


class TreeNode(BaseModel):
    name: str
    size: int
    children: List["TreeNode"]
    # The folder name when this node is a mod folder that can be uploaded.
    unit: Optional[str]
    invalid: bool


class Transfer(BaseModel):
    label: str
    done: int
    total: int
    speed: float


# The GitHub tab's state. The *_list and tree counters grow when their list changes, so the tab
# repaints only what did.
class UploadJob(BaseModel):
    # Updated field by field while it runs, so each change is checked too.
    model_config = ConfigDict(validate_assignment=True)

    phase: str = "idle"
    folders: List[Folder] = []
    repos: List[str] = []
    repo_details: List[Repo] = []
    repo_list: int = 0
    releases: List[str] = []
    # The release GitHub marks as latest, which the list puts first; empty when there is none.
    latest_release: str = ""
    release_list: int = 0
    assets: List[Asset] = []
    asset_list: int = 0
    fresh_assets: List[str] = []
    fresh_folders: List[str] = []
    tree_nodes: List[TreeNode] = []
    select_tag: str = ""
    tree: int = 0
    done: int = 0
    total: int = 0
    message: str = ""
    failed: bool = False
    alerts: int = 0
    runs: int = 0
    source: str = ""
    source_list: int = 0
    transfer: Optional[Transfer] = None
    item_progress: Dict[str, str] = {}
    # The release shown beside the chosen one while comparing them; empty when not comparing.
    compare_tag: str = ""
    compare_assets: List[Asset] = []
    compare_list: int = 0
    # What the last upload or download failed on, so Retry all can run it again on the same release.
    retry_kind: str = ""
    retry_names: List[str] = []
    retry_tag: str = ""


# One file of a release, or the parts of one file, as the comparison of two releases shows it.
class CompareRow(BaseModel):
    key: str
    files: List[str]
    size: int
    updated: str
    # The game and its "[mod] - [version]", from the label; empty for a file without one.
    game: str
    variant: str
    # "same" (on both), "differs" (the other has the game in another mod or version) or "only".
    state: str = ""
    # The other release's variants of the game, for "differs".
    other: List[str] = []


class UploadSnapshot(UploadJob):
    log: List[LogEntry]
    gh_ready: Optional[bool]


# A saved mod waiting for its automatic upload.
class AutoMod(BaseModel):
    id: str
    # Entries of the same file, recorded in state.json with it.
    twins: List[str]
    sha256: str
    version: str
    game_version: str
    size: int
    game: str


class AutoUpload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    mod: AutoMod
    folder: Path
    tag: str
    old: str
    cancel: threading.Event


class AssetIdentity(BaseModel):
    game: str = ""
    variant: str = ""


class ReleaseComparison(BaseModel):
    left: List[CompareRow]
    right: List[CompareRow]


class ReleaseRenames(BaseModel):
    repos: List[str]
    notes: List[str]


class UploadPart(BaseModel):
    name: str
    path: Path


class RetryState(BaseModel):
    kind: str = ""
    names: List[str] = []
    tag: str = ""
