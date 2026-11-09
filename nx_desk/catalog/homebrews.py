from typing import List, Set

from ..schemas.feeds import HomebrewInput, ListFeed
from ..schemas.homebrew import Homebrew
from ..utils.urls import https_or_empty
from .values import as_text


def parse_homebrews(data: object) -> List[Homebrew]:
    try:
        feed = ListFeed.model_validate(obj=data)

    except ValueError:
        return []

    raw_rows = feed.homebrews
    rows: List[Homebrew] = []
    seen: Set[str] = set()

    for raw in raw_rows if isinstance(raw_rows, list) else ():
        try:
            source = HomebrewInput.model_validate(obj=raw)

        except ValueError:
            continue

        key, name = as_text(value=source.id).strip()[:300], as_text(value=source.name).strip()[:300]

        if not key or not name or key in seen:
            continue

        groups = source.groups
        row = Homebrew.model_validate(
            obj={
                "description": as_text(value=source.description).strip()[:4000],
                "category": as_text(value=source.category).strip()[:500],
                "version": as_text(value=source.version).strip()[:500],
                "authors": as_text(value=source.authors).strip()[:500],
                "updated": as_text(value=source.updated).strip()[:500],
                "id": key,
                "name": name,
                "groups": list(
                    dict.fromkeys(group.strip()[:100] for group in groups if isinstance(group, str) and group.strip()),
                )
                if isinstance(groups, list)
                else [],
                "url": https_or_empty(value=source.url),
            },
        )
        seen.add(key)
        rows.append(row)

    return rows


def find_homebrews(rows: List[Homebrew], query: str) -> List[Homebrew]:
    words = query.casefold().split()

    return [
        row
        for row in rows
        if all(
            word
            in " ".join((row.name, row.description, *row.groups, row.category, row.version, row.authors)).casefold()
            for word in words
        )
    ]
