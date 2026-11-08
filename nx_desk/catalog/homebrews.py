from ..schemas.homebrew import Homebrew
from .values import as_text, https_or_empty


def parse_homebrews(data: object) -> list[Homebrew]:
    raw_rows = data.get("homebrews") if isinstance(data, dict) else None
    rows: list[Homebrew] = []
    seen: set[str] = set()

    for raw in raw_rows if isinstance(raw_rows, list) else ():
        if not isinstance(raw, dict):
            continue

        key, name = (as_text(value=raw.get(field)).strip()[:300] for field in ("id", "name"))

        if not key or not name or key in seen:
            continue

        groups = raw.get("groups")
        clean = {
            field: as_text(value=raw.get(field)).strip()[: 4000 if field == "description" else 500]
            for field in ("description", "category", "version", "authors", "updated")
        }
        row = Homebrew.model_validate(
            obj={
                **clean,
                "id": key,
                "name": name,
                "groups": list(
                    dict.fromkeys(group.strip()[:100] for group in groups if isinstance(group, str) and group.strip()),
                )
                if isinstance(groups, list)
                else [],
                "url": https_or_empty(value=raw.get("url")),
            },
        )
        seen.add(key)
        rows.append(row)

    return rows


def find_homebrews(rows: list[Homebrew], query: str) -> list[Homebrew]:
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
