import re
from typing import Dict, List
from urllib.parse import quote

from pydantic import TypeAdapter

from ..schemas.api import AssetUpdate, ReleaseCreate, ReleasePayload, ReleaseUpdate, RepositoryPayload
from ..schemas.github import Asset, Repo
from . import api, archive, command

REPO_NAME = re.compile(pattern=r"^[\w.-]+/[\w.-]+$")


def list_repos() -> List[Repo]:
    repos: List[Repo] = []

    for raw in api.pages(path="user/repos"):
        if not isinstance(raw, dict):
            continue

        row = RepositoryPayload.model_validate(obj=raw)

        if not REPO_NAME.fullmatch(string=row.full_name):
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


def by_tag(repo: str, tag: str) -> ReleasePayload:
    return ReleasePayload.model_validate(
        obj=api.request(path=f"repos/{repo}/releases/tags/{quote(string=tag, safe='')}"),
    )


def latest_release(repo: str) -> str:
    try:
        return ReleasePayload.model_validate(obj=api.request(path=f"repos/{repo}/releases/latest")).tag_name

    except command.GitHubError as error:
        if error.status != 404:
            raise

        return ""


def list_releases(repo: str) -> List[str]:
    releases = RELEASES.validate_python(api.pages(path=f"repos/{repo}/releases"))

    return [release.tag_name for release in releases]


def create_release(repo: str, tag: str) -> None:
    api.request(path=f"repos/{repo}/releases", method="POST", data=ReleaseCreate(tag_name=tag, name=tag))


def rename_release(repo: str, tag: str, new_tag: str) -> None:
    release = by_tag(repo=repo, tag=tag)
    api.request(
        path=f"repos/{repo}/releases/{release.id}",
        method="PATCH",
        data=ReleaseUpdate(tag_name=new_tag, name=new_tag),
    )


def delete_tag(repo: str, tag: str) -> bool:
    try:
        api.request(path=f"repos/{repo}/git/refs/tags/{quote(string=tag, safe='')}", method="DELETE")

    except command.GitHubError as error:
        return error.status in (404, 422)

    return True


def delete_release(repo: str, tag: str) -> None:
    release = by_tag(repo=repo, tag=tag)
    api.request(path=f"repos/{repo}/releases/{release.id}", method="DELETE")

    if not delete_tag(repo=repo, tag=tag):
        raise command.GitHubError("Release deleted, but its Git tag could not be removed")


def remote_assets(repo: str, tag: str) -> Dict[str, Asset]:
    release = by_tag(repo=repo, tag=tag)
    assets = ASSETS.validate_python(api.pages(path=f"repos/{repo}/releases/{release.id}/assets"))

    return {asset.name: asset for asset in assets}


def delete_asset(repo: str, asset: Asset) -> None:
    try:
        api.request(path=f"repos/{repo}/releases/assets/{asset.id}", method="DELETE")

    except command.GitHubError as error:
        if error.status != 404:
            raise


def rename_asset(repo: str, asset: Asset, name: str, label: str = "") -> None:
    api.request(
        path=f"repos/{repo}/releases/assets/{asset.id}",
        method="PATCH",
        data=AssetUpdate(name=name, label=label or None),
    )


def delete_leftovers(repo: str, tag: str) -> List[str]:
    leftovers = [
        asset for name, asset in remote_assets(repo=repo, tag=tag).items() if name.startswith(archive.TEMP_PREFIX)
    ]

    for asset in leftovers:
        delete_asset(repo=repo, asset=asset)

    return [asset.name for asset in leftovers]


RELEASES: TypeAdapter[List[ReleasePayload]] = TypeAdapter(type=List[ReleasePayload])
ASSETS: TypeAdapter[List[Asset]] = TypeAdapter(type=List[Asset])
