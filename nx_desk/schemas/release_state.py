import re
from typing import TYPE_CHECKING, Dict, List, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


# Keep this contract identical in both applications.
class ReleaseRecord(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)

    if not TYPE_CHECKING:
        __pydantic_extra__: Dict[str, JsonValue] = Field(init=False)

    sha256: str = ""
    version: str = ""
    game_version: str = ""
    folder: str = ""
    files: List[str] = Field(default_factory=list)
    uploaded_at: str = ""

    @field_validator("version", "game_version", "folder", "uploaded_at", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        return value.strip() if isinstance(value, str) else ""

    @field_validator("sha256", mode="before")
    @classmethod
    def _hash(cls, value: object) -> str:
        return value.strip().lower() if isinstance(value, str) else ""

    @field_validator("files", mode="before")
    @classmethod
    def _files(cls, value: object) -> List[str]:
        if not isinstance(value, list):
            return []

        return sorted({item for item in value if isinstance(item, str) and item.strip()})


class ReleaseDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)

    version: Literal[1] = 1
    catalog: str = ""
    mods: Dict[str, ReleaseRecord] = Field(default_factory=dict)

    @field_validator("catalog", mode="before")
    @classmethod
    def _catalog(cls, value: object) -> str:
        text = value.strip() if isinstance(value, str) else ""
        url = urlsplit(url=text)
        parts = url.path.split(sep="/")

        if (
            url.hostname == "gist.githubusercontent.com"
            and len(parts) >= 6
            and parts[3] == "raw"
            and re.fullmatch(pattern=r"[a-fA-F0-9]{40}", string=parts[4])
        ):
            return urlunsplit(
                components=(url.scheme, url.netloc, "/".join([*parts[:4], *parts[5:]]), url.query, url.fragment),
            )

        return text
