from typing import Dict, List, Literal

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
    tags: List[str]
    description: List[str]
    highlights: List[Highlight]
    done: List[str]
    kept: List[str]
    changelog: str
    credit: str
    cover: str
    background: str
    sha256: str
    size: int
    urls: List[str]
    # The catalog's own name, kept when the titledb name replaces it; empty until then.
    catalog_name: str = ""
    # The name its saved folder takes, shared by every entry of the same file; empty until named.
    save_name: str = ""
    # Other entries of the catalog with the same file, which share its download.
    twins: List[str] = []


# A parsed catalog: its games.
class CatalogDocument(BaseModel):
    items: List[Mod]


# A catalog in the registry.
class Catalog(BaseModel):
    name: str
    url: str
    folder: str
    # Canonical field -> the catalog's own key, for catalogs with unusual names.
    mapping: Dict[str, str] = {}


# What editing a catalog did: the catalog, how many games it holds and what else changed, such as its release.
class CatalogEdit(BaseModel):
    catalog: Catalog
    count: int
    notes: List[str] = []


class CatalogFetch(BaseModel):
    raw: bytes
    document: CatalogDocument


class CatalogChanges(BaseModel):
    added: List[str]
    changed: List[str]


class CatalogSource(BaseModel):
    url: str
    mapping: Dict[str, str]
