from typing import List, Optional

from pydantic import BaseModel, JsonValue, field_validator


class GitHubOwner(BaseModel):
    login: str = ""

    @field_validator("login", mode="before")
    @classmethod
    def _login(cls, value: object) -> str:
        return value if isinstance(value, str) else ""


class RepositoryPayload(BaseModel):
    full_name: str = ""
    name: str = ""
    owner: Optional[GitHubOwner] = None
    visibility: str = ""
    description: str = ""
    updated_at: str = ""

    @field_validator("full_name", "name", "visibility", "description", "updated_at", mode="before")
    @classmethod
    def _text(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    @field_validator("owner", mode="before")
    @classmethod
    def _owner(cls, value: object) -> Optional[GitHubOwner]:
        return GitHubOwner.model_validate(obj=value) if isinstance(value, dict) else None


# Preserve malformed optional asset fields as missing so selection can reject that asset.
class ReleaseDownload(BaseModel):
    name: str = ""
    browser_download_url: Optional[str] = None
    size: Optional[int] = None
    digest: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: object) -> str:
        return value if isinstance(value, str) else ""

    @field_validator("browser_download_url", "digest", mode="before")
    @classmethod
    def _text(cls, value: object) -> Optional[str]:
        return value if isinstance(value, str) else None

    @field_validator("size", mode="before")
    @classmethod
    def _size(cls, value: object) -> Optional[int]:
        return value if isinstance(value, int) and not isinstance(value, bool) else None


class ReleasePayload(BaseModel):
    id: int = 0
    tag_name: str = ""
    html_url: str = ""
    assets: List[ReleaseDownload] = []

    @field_validator("assets", mode="before")
    @classmethod
    def _assets(cls, value: object) -> List[ReleaseDownload]:
        if not isinstance(value, list):
            return []

        return [ReleaseDownload.model_validate(obj=row) for row in value if isinstance(row, dict)]


class GitHubError(BaseModel):
    message: str = ""


class SteamReply(BaseModel):
    success: bool = False
    data: Optional[List[JsonValue]] = None

    @field_validator("success", mode="before")
    @classmethod
    def _success(cls, value: object) -> bool:
        return value is True

    @field_validator("data", mode="before")
    @classmethod
    def _data(cls, value: object) -> object:
        return value if isinstance(value, list) else None


class SteamGame(BaseModel):
    id: int
    name: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def _id(cls, value: object) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError("game id must be a positive integer")

        return value

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, value: object) -> Optional[str]:
        return value if isinstance(value, str) else None


class SteamImage(BaseModel):
    url: str
