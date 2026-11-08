import json
import time
from typing import Any

from .. import net
from ..config import MAX_CATALOG, SAFE_ID, SAFE_SHA
from ..names import art_slug
from ..schemas.catalog import CatalogDocument, Highlight, Mod
from .fields import ROOT_ALIASES
from .values import as_list, as_size, as_text, dig, https_or_empty, pick, resolve_urls


def normalize(raw: object, mapping: dict[str, str] | None = None) -> Mod | None:
    # Catalog data is untrusted. An id and one https URL are required, the rest may be missing.
    if not isinstance(raw, dict):
        return None

    def get(field: str) -> Any:
        return pick(raw=raw, field=field, mapping=mapping)

    name = as_text(value=get(field="name")).strip()
    raw_id = get(field="id")
    # A catalog keyed only by name gets an id derived from it; an id that is present but
    # unsafe is rejected rather than papered over.
    entry_id = art_slug(name=name)[:64] if raw_id is None else as_text(value=raw_id).strip()

    if not SAFE_ID.match(string=entry_id):
        return None

    urls = resolve_urls(primary=get(field="url"), mirrors=get(field="mirrors"))

    if not urls:
        return None

    sha = as_text(value=get(field="sha256")).strip().lower()
    sha = sha if SAFE_SHA.match(string=sha) else ""
    size = max(0, as_size(value=get(field="size")))

    return Mod(
        id=entry_id,
        name=name or entry_id,
        version=as_text(value=get(field="version")),
        game_version=as_text(value=get(field="game_version")),
        title_id=as_text(value=get(field="title_id")),
        tagline=as_text(value=get(field="tagline")),
        developer=as_text(value=get(field="developer")),
        release=as_text(value=get(field="release")),
        translator=as_text(value=get(field="translator")),
        tags=[as_text(value=tag) for tag in as_list(value=get(field="tags")) if as_text(value=tag)],
        description=[as_text(value=line) for line in as_list(value=get(field="description"))],
        highlights=[
            Highlight(
                title=as_text(value=dig(obj=entry, path="title")),
                text=as_text(value=dig(obj=entry, path="text")),
            )
            for entry in as_list(value=get(field="highlights"))
            if isinstance(entry, dict)
        ],
        done=[as_text(value=line) for line in as_list(value=get(field="done"))],
        kept=[as_text(value=line) for line in as_list(value=get(field="kept"))],
        changelog=as_text(value=get(field="changelog")),
        credit=as_text(value=get(field="credit")),
        cover=https_or_empty(value=get(field="cover")),
        background=https_or_empty(value=get(field="background")),
        sha256=sha,
        size=size,
        urls=urls,
    )


def find_rows(data: object, mapping: dict[str, str] | None) -> list[Any] | None:
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return None

    if mapping and mapping.get("__root__"):
        rows = dig(obj=data, path=mapping["__root__"])

        return rows if isinstance(rows, list) else None

    for key in ROOT_ALIASES:
        if isinstance(data.get(key), list):
            return data[key]

    return None


def fetch_catalog(url: str, mapping: dict[str, str] | None = None) -> tuple[bytes, CatalogDocument]:
    separator = "&" if "?" in url else "?"

    with net.http_get(url=f"{url}{separator}t={int(time.time())}") as response:
        raw = response.read(MAX_CATALOG + 1)

    if len(raw) > MAX_CATALOG:
        raise ValueError("catalog is too large")

    return raw, parse_catalog(data=json.loads(s=raw), mapping=mapping)


def parse_catalog(data: object, mapping: dict[str, str] | None = None) -> CatalogDocument:
    rows = find_rows(data=data, mapping=mapping)

    if rows is None:
        raise ValueError("file is not a catalog")

    items: list[Mod] = []
    seen: set[str] = set()

    for raw in rows:
        entry = normalize(raw=raw, mapping=mapping)

        if entry and entry.id not in seen:
            seen.add(entry.id)
            items.append(entry)

    if not items:
        raise ValueError("catalog has no valid games")

    return CatalogDocument(items=items)
