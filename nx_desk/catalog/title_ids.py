from typing import Dict, List

from ..config import TITLE_ID
from ..schemas.feeds import TitleFeed, TitleInput
from ..schemas.title import TitleRow


def game_kind(title: str) -> str:
    low = int(title, 16) & 0x1FFF

    return "Game" if not low else "Update" if low == 0x800 else "DLC"


# The merged list from the nx-index repository: id, name, section and detail for each title.
def parse_title_ids(data: object) -> List[TitleRow]:
    rows: List[TitleRow] = []

    try:
        feed = TitleFeed.model_validate(obj=data)

    except ValueError:
        return rows

    for section, titles in (("games", feed.games), ("system", feed.system), ("sysmodules", feed.sysmodules)):
        for title, value in titles.items():
            try:
                source = (
                    TitleInput.model_validate(obj=value)
                    if isinstance(value, dict)
                    else TitleInput(name=value, group="")
                )

            except ValueError:
                continue

            name, detail = source.name, source.group

            if TITLE_ID.match(string=title) and isinstance(name, str) and name.strip():
                shown = game_kind(title=title) if section == "games" else str(detail or "Homebrew")
                rows.append(TitleRow(id=title.upper(), name=name.strip(), section=section, detail=shown))

    return rows


# A full ID also finds its game: updates and DLC share the upper part of an ID whose last 13 bits
# are zero. System IDs do not follow that rule, so only games count as a match that way.
def find_titles[Row: TitleRow](rows: List[Row], query: str) -> List[Row]:

    if not query:
        return rows

    if TITLE_ID.match(string=query):
        title = query.upper()
        base = f"{int(title, 16) & ~0x1FFF:016X}"

        return [row for row in rows if row.id == title or (row.id == base and row.section == "games")]

    text = query.casefold()

    return [row for row in rows if text in f"{row.id} {row.name} {row.detail}".casefold()]


# Official game names by title ID, from the games section of the list.
def game_names(rows: List[TitleRow]) -> Dict[str, str]:
    return {row.id: row.name for row in rows if row.section == "games"}
