from typing import List

from pydantic import BaseModel

from .catalog import Highlight


class ExampleMod(BaseModel):
    id: str
    title_id: str
    name: str
    game_version: str
    mod_version: str
    sha256: str
    size: int
    url: str
    mirrors: List[str]
    tagline: str
    developer: str
    release: str
    translator: str
    tags: List[str]
    description: List[str]
    highlights: List[Highlight]
    done: List[str]
    kept: List[str]
    changelog: str
    credit: str
    cover: str
    background: str


class CatalogExample(BaseModel):
    mods: List[ExampleMod]
