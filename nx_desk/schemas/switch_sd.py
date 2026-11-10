from pathlib import Path
from typing import Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

SDCategory = Literal["Game", "System content", "Sysmodule", ""]


class SDContentIdentity(BaseModel):
    name: str = ""
    category: SDCategory = ""


class MountedVolume(BaseModel):
    root: Path
    label: str = ""
    filesystem: str
    device: str = ""
    read_only: bool = False


class SwitchCard(MountedVolume):
    markers: List[str]
    identity: List[int]


class SDPackageInfo(BaseModel):
    id: str
    name: str
    mod_version: str = ""
    game_version: str = ""


class SDManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    packages: List[SDPackageInfo]
    files: Dict[str, str]


class SDTitle(BaseModel):
    title_id: str
    name: str
    kinds: List[str]
    size: int
    files: int
    category: SDCategory = ""
    status: str = ""
    mod_version: str = ""
    target_game: str = ""


class SDSnapshot(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    cards: List[SwitchCard] = Field(default_factory=list)
    selected: str = ""
    titles: List[SDTitle] = Field(default_factory=list)
    revision: int = 0
    phase: str = "idle"
    message: str = "Connect a Switch CFW card or expose it through USB mass storage."
    failed: bool = False
