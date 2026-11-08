import json
import re
from urllib.parse import quote

from ..schemas.github import Asset, Repo
from . import archive, command

REPO_NAME = re.compile(pattern=r"^[\w.-]+/[\w.-]+$")
# What GitHub says when a tag is not there: already gone, which is what a delete wants.
TAG_GONE = re.compile(pattern=r"HTTP 404|HTTP 422|Reference does not exist|Not Found", flags=re.IGNORECASE)


# Every repository the user owns, works on with others or reaches through an organization, so two of
# the same name under different owners both show.
def list_repos() -> list[Repo]:
    pages = json.loads(s=command.gh("api", "--paginate", "--slurp", "user/repos?per_page=100"))
    repos = []

    for row in (row for page in pages for row in page if isinstance(row, dict)):
        full_name = row.get("full_name")

        if not isinstance(full_name, str) or not REPO_NAME.match(string=full_name):
            continue

        owner = row.get("owner")
        fields = {
            "name": row.get("name"),
            "owner": owner.get("login") if isinstance(owner, dict) else None,
            "visibility": row.get("visibility"),
            "description": row.get("description"),
            "updated_at": row.get("updated_at"),
        }
        repos.append(
            Repo(full_name=full_name, **{key: value for key, value in fields.items() if isinstance(value, str)}),
        )

    return sorted(repos, key=lambda repo: repo.full_name.casefold())


def latest_release(repo: str) -> str:
    try:
        return json.loads(s=command.gh("api", f"repos/{repo}/releases/latest"))["tag_name"]
    except command.GhError:
        return ""


def list_releases(repo: str) -> list[str]:
    pages = json.loads(s=command.gh("api", "--paginate", "--slurp", f"repos/{repo}/releases?per_page=100"))

    return [release["tag_name"] for page in pages for release in page]


def create_release(repo: str, tag: str) -> None:
    command.gh("release", "create", tag, "--repo", repo, "--title", tag, "--notes", "", "--latest=false")


def rename_release(repo: str, tag: str, new_tag: str) -> None:
    command.gh("release", "edit", tag, "--repo", repo, "--tag", new_tag, "--title", new_tag)


# Renaming a release leaves its old git tag in the repository, with no file on it. For a release the app made,
# the tag is its own, so this removes it. True when the tag is gone, whether it was removed now or already.
def delete_tag(repo: str, tag: str) -> bool:
    try:
        command.gh("api", "-X", "DELETE", f"repos/{repo}/git/refs/tags/{quote(tag, safe='')}")
    except command.GhError as error:
        return bool(TAG_GONE.search(string=str(error)))

    return True


def delete_release(repo: str, tag: str) -> None:
    command.gh("release", "delete", tag, "--repo", repo, "--yes", "--cleanup-tag")


def remote_assets(repo: str, tag: str) -> dict[str, Asset]:
    release = json.loads(s=command.gh("api", f"repos/{repo}/releases/tags/{tag}"))
    pages = json.loads(
        s=command.gh("api", "--paginate", "--slurp", f"repos/{repo}/releases/{release['id']}/assets?per_page=100"),
    )

    return {asset["name"]: Asset.model_validate(asset) for page in pages for asset in page}


def delete_asset(repo: str, asset: Asset) -> None:
    try:
        command.gh("api", "-X", "DELETE", f"repos/{repo}/releases/assets/{asset.id}")
    except command.GhError as error:
        # Already gone, such as when a try that GitHub reported as failed did delete it.
        if "HTTP 404" not in str(error):
            raise


# Files left under a temporary name by an upload that stopped halfway.
def delete_leftovers(repo: str, tag: str) -> list[str]:
    leftovers = [
        asset for name, asset in remote_assets(repo=repo, tag=tag).items() if name.startswith(archive.TEMP_PREFIX)
    ]

    for asset in leftovers:
        delete_asset(repo=repo, asset=asset)

    return [asset.name for asset in leftovers]
