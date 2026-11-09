import re
from typing import Dict, List
from urllib.parse import quote

from pydantic import JsonValue, TypeAdapter

from ..schemas.api import ReleasePayload, RepositoryPayload
from ..schemas.github import Asset, Repo
from ..utils.json import parse_json
from . import archive, command

REPO_NAME = re.compile(pattern=r"^[\w.-]+/[\w.-]+$")
# What GitHub says when a tag is not there: already gone, which is what a delete wants.
TAG_GONE = re.compile(pattern=r"HTTP 404|HTTP 422|Reference does not exist|Not Found", flags=re.IGNORECASE)


# Every repository the user owns, works on with others or reaches through an organization, so two of
# the same name under different owners both show.
def list_repos() -> List[Repo]:
    pages = PAGES.validate_python(
        parse_json(text=command.gh("api", "--paginate", "--slurp", "user/repos?per_page=100")),
    )
    repos: List[Repo] = []

    for raw in (row for page in pages for row in page if isinstance(row, dict)):
        row = RepositoryPayload.model_validate(obj=raw)

        if not REPO_NAME.match(string=row.full_name):
            continue

        repos.append(
            Repo(
                full_name=row.full_name,
                name=row.name,
                owner=row.owner.login if row.owner else "",
                visibility=row.visibility,
                description=row.description,
                updated_at=row.updated_at,
            ),
        )

    return sorted(repos, key=lambda repo: repo.full_name.casefold())


def latest_release(repo: str) -> str:
    try:
        return ReleasePayload.model_validate_json(json_data=command.gh("api", f"repos/{repo}/releases/latest")).tag_name

    except command.GhError:
        return ""


def list_releases(repo: str) -> List[str]:
    pages = RELEASES.validate_json(command.gh("api", "--paginate", "--slurp", f"repos/{repo}/releases?per_page=100"))

    return [release.tag_name for page in pages for release in page]


def create_release(repo: str, tag: str) -> None:
    command.gh("release", "create", tag, "--repo", repo, "--title", tag, "--notes", "", "--latest=false")


def rename_release(repo: str, tag: str, new_tag: str) -> None:
    command.gh("release", "edit", tag, "--repo", repo, "--tag", new_tag, "--title", new_tag)


# Renaming a release leaves its old git tag in the repository, with no file on it. For a release the app made,
# the tag is its own, so this removes it. True when the tag is gone, whether it was removed now or already.
def delete_tag(repo: str, tag: str) -> bool:
    try:
        command.gh("api", "-X", "DELETE", f"repos/{repo}/git/refs/tags/{quote(string=tag, safe='')}")

    except command.GhError as error:
        return bool(TAG_GONE.search(string=str(error)))

    return True


def delete_release(repo: str, tag: str) -> None:
    command.gh("release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag")


def remote_assets(repo: str, tag: str) -> Dict[str, Asset]:
    release = ReleasePayload.model_validate_json(json_data=command.gh("api", f"repos/{repo}/releases/tags/{tag}"))
    pages = ASSETS.validate_json(
        command.gh("api", "--paginate", "--slurp", f"repos/{repo}/releases/{release.id}/assets?per_page=100"),
    )

    return {asset.name: asset for page in pages for asset in page}


def delete_asset(repo: str, asset: Asset) -> None:
    try:
        command.gh("api", "-X", "DELETE", f"repos/{repo}/releases/assets/{asset.id}")

    except command.GhError as error:
        # Already gone, such as when a try that GitHub reported as failed did delete it.
        if "HTTP 404" not in str(error):
            raise


# Files left under a temporary name by an upload that stopped halfway.
def delete_leftovers(repo: str, tag: str) -> List[str]:
    leftovers = [
        asset for name, asset in remote_assets(repo=repo, tag=tag).items() if name.startswith(archive.TEMP_PREFIX)
    ]

    for asset in leftovers:
        delete_asset(repo=repo, asset=asset)

    return [asset.name for asset in leftovers]


PAGES: TypeAdapter[List[List[JsonValue]]] = TypeAdapter(type=List[List[JsonValue]])
RELEASES: TypeAdapter[List[List[ReleasePayload]]] = TypeAdapter(type=List[List[ReleasePayload]])
ASSETS: TypeAdapter[List[List[Asset]]] = TypeAdapter(type=List[List[Asset]])
