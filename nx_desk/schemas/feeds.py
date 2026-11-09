from typing import Dict, List

from pydantic import BaseModel, JsonValue, field_validator


# Values remain JSON until each feed applies its display and URL normalization.
class HomebrewInput(BaseModel):
    id: JsonValue = None
    name: JsonValue = None
    description: JsonValue = None
    groups: JsonValue = None
    category: JsonValue = None
    version: JsonValue = None
    authors: JsonValue = None
    updated: JsonValue = None
    url: JsonValue = None


class PortInput(BaseModel):
    id: JsonValue = None
    name: JsonValue = None
    platform: JsonValue = None
    kind: JsonValue = None
    emulates: JsonValue = None
    version: JsonValue = None
    updated: JsonValue = None
    url: JsonValue = None
    host: JsonValue = None
    thread: JsonValue = None
    status: JsonValue = None


class ListFeed(BaseModel):
    homebrews: List[JsonValue] = []
    ports: List[JsonValue] = []

    @field_validator("homebrews", "ports", mode="before")
    @classmethod
    def _rows(cls, value: object) -> object:
        return value if isinstance(value, list) else []


class TitleInput(BaseModel):
    name: JsonValue = None
    group: JsonValue = None


class TitleFeed(BaseModel):
    games: Dict[str, JsonValue] = {}
    system: Dict[str, JsonValue] = {}
    sysmodules: Dict[str, JsonValue] = {}

    @field_validator("games", "system", "sysmodules", mode="before")
    @classmethod
    def _titles(cls, value: object) -> object:
        if not isinstance(value, dict):
            return {}

        return {key: item for key, item in value.items() if isinstance(key, str)}
