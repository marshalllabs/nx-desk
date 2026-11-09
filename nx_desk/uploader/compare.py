from typing import Dict, List

from ..names import game_of
from ..schemas.github import Asset, AssetIdentity, CompareRow, ReleaseComparison
from .parts import group_key


# A release file's game and its "[mod] - [version]", from the folder name upload_parts puts in its label.
def variant_of(label: str) -> AssetIdentity:
    game = game_of(folder=label)

    return AssetIdentity(game=game, variant=label[len(game) + len(" - ") :]) if game else AssetIdentity()


# The release files grouped as one row per file, joining the parts of a split one.
def group_rows(assets: List[Asset]) -> Dict[str, CompareRow]:
    groups: Dict[str, List[Asset]] = {}

    for asset in assets:
        groups.setdefault(group_key(name=asset.name), []).append(asset)

    rows = {}

    for key, members in groups.items():
        identity = next(
            (found for member in members if (found := variant_of(label=member.label or "")).game),
            AssetIdentity(),
        )
        rows[key] = CompareRow(
            key=key,
            files=sorted(member.name for member in members),
            size=sum(member.size for member in members),
            updated=max(member.updated_at for member in members)[:10],
            game=identity.game,
            variant=identity.variant,
        )

    return rows


# Files match by name. A file missing from the other release still "differs" when that release has
# the same game under another mod or version, and is "only" on this one otherwise.
def mark(rows: Dict[str, CompareRow], other: Dict[str, CompareRow]) -> List[CompareRow]:
    games: Dict[str, List[str]] = {}

    for row in other.values():
        if row.game:
            games.setdefault(row.game.casefold(), []).append(row.variant or row.key)

    marked = []

    for key, row in sorted(rows.items()):
        if key in other:
            state, others = "same", []

        elif row.game and row.game.casefold() in games:
            state, others = "differs", sorted(games[row.game.casefold()])

        else:
            state, others = "only", []

        marked.append(row.model_copy(update={"state": state, "other": others}))

    return marked


def compare_releases(left: List[Asset], right: List[Asset]) -> ReleaseComparison:
    first, second = group_rows(assets=left), group_rows(assets=right)

    return ReleaseComparison(left=mark(rows=first, other=second), right=mark(rows=second, other=first))
