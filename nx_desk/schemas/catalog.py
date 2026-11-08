from typing import Literal

from pydantic import BaseModel

ArtKind = Literal["cover", "background"]


class Highlight(BaseModel):
    title: str
    text: str


# One game of a catalog, after catalog.normalize.
class Mod(BaseModel):
    id: str
    name: str
    version: str
    game_version: str
    title_id: str
    tagline: str
    developer: str
    release: str
    translator: str
    tags: list[str]
    description: list[str]
    highlights: list[Highlight]
    done: list[str]
    kept: list[str]
    changelog: str
    credit: str
    cover: str
    background: str
    sha256: str
    size: int
    urls: list[str]
    # The catalog's own name, kept when the titledb name replaces it; empty until then.
    catalog_name: str = ""
    # The name its saved folder takes, shared by every entry of the same file; empty until named.
    save_name: str = ""
    # Other entries of the catalog with the same file, which share its download.
    twins: list[str] = []


# A parsed catalog: its games.
class CatalogDocument(BaseModel):
    items: list[Mod]


# A catalog in the registry.
class Catalog(BaseModel):
    name: str
    url: str
    folder: str
    # Canonical field -> the catalog's own key, for catalogs with unusual names.
    mapping: dict[str, str] = {}


# What editing a catalog did: the catalog, how many games it holds and what else changed, such as its release.
class CatalogEdit(BaseModel):
    catalog: Catalog
    count: int
    notes: list[str] = []
