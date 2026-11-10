import json
from pathlib import Path
from typing import Dict

from ..schemas.github import Asset
from ..schemas.release_state import ReleaseDocument, ReleaseRecord
from ..utils.files import sha256_of
from . import archive, command, download, progress, releases, upload

# What each release linked to a catalog holds, for telling what was uploaded once local copies are gone.
STATE_ASSET = "state.json"


def clean_state(data: object) -> Dict[str, ReleaseRecord]:
    document = ReleaseDocument.model_validate(obj=data)

    return dict(document.mods)


def read_state(repo: str, tag: str, asset: Asset, place: Path) -> Dict[str, ReleaseRecord]:
    path = place / STATE_ASSET
    progress.transfer(
        action=lambda: download.asset(repo=repo, asset_id=asset.id, target=path),
        report=lambda text: None,
        name=STATE_ASSET,
        partial=path,
    )
    digest = asset.digest

    if digest and digest != f"sha256:{sha256_of(path=path)}":
        raise command.GitHubError(f"{STATE_ASSET}: downloaded file does not match SHA-256")

    try:
        return clean_state(data=json.loads(s=path.read_text(encoding="utf-8")))

    except ValueError as error:
        raise command.GitHubError(f"{STATE_ASSET} on release {tag} is not valid JSON") from error


# The new copy goes up under a temporary name and is checked before the old one is removed.
def replace_asset(repo: str, tag: str, path: Path) -> str:
    temp = path.with_name(name=archive.TEMP_PREFIX + path.name)
    path.rename(target=temp)
    upload.upload_file(repo=repo, tag=tag, path=temp)
    fresh = releases.remote_assets(repo=repo, tag=tag)
    digest = f"sha256:{sha256_of(path=temp)}"

    if fresh[temp.name].digest != digest:
        raise command.GitHubError(f"{path.name}: file on GitHub does not match, the old copy is kept")

    if path.name in fresh:
        releases.delete_asset(repo=repo, asset=fresh[path.name])

    releases.rename_asset(repo=repo, asset=fresh[temp.name], name=path.name)

    return digest
