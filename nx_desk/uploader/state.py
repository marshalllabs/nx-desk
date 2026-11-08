import json
from pathlib import Path

from ..schemas.github import Asset
from ..schemas.state import ReleaseRecord
from ..utils.files import sha256_of
from . import archive, command, releases, upload

# What each release linked to a catalog holds, for telling what was uploaded once local copies are gone.
STATE_ASSET = "state.json"


def clean_state(data: object) -> dict[str, ReleaseRecord]:
    mods = data.get("mods") if isinstance(data, dict) else None

    if not isinstance(mods, dict):
        return {}

    fields = ("sha256", "version", "game_version", "folder", "uploaded_at")
    clean: dict[str, ReleaseRecord] = {}

    for key, record in mods.items():
        if isinstance(key, str) and isinstance(record, dict):
            # Only the string fields of each record survive, so the result fits the schema.
            kept = {field: record[field] for field in fields if isinstance(record.get(field), str)}
            files = record.get("files")
            names = [name for name in files if isinstance(name, str)] if isinstance(files, list) else []
            clean[key] = ReleaseRecord(**kept, files=names)

    return clean


def read_state(repo: str, tag: str, asset: Asset, place: Path) -> dict[str, ReleaseRecord]:
    command.gh("release", "download", tag, "--repo", repo, "--pattern", STATE_ASSET, "--dir", str(place))
    path = place / STATE_ASSET
    digest = asset.digest

    if digest and digest != f"sha256:{sha256_of(path=path)}":
        raise command.GhError(f"{STATE_ASSET}: downloaded file does not match SHA-256")

    try:
        return clean_state(data=json.loads(s=path.read_text(encoding="utf-8")))
    except ValueError as error:
        raise command.GhError(f"{STATE_ASSET} on release {tag} is not valid JSON") from error


# The new copy goes up under a temporary name and is checked before the old one is removed.
def replace_asset(repo: str, tag: str, path: Path) -> str:
    temp = path.with_name(name=archive.TEMP_PREFIX + path.name)
    path.rename(target=temp)
    upload.upload_file(repo=repo, tag=tag, path=temp)
    fresh = releases.remote_assets(repo=repo, tag=tag)
    digest = f"sha256:{sha256_of(path=temp)}"

    if fresh[temp.name].digest != digest:
        raise command.GhError(f"{path.name}: file on GitHub does not match, the old copy is kept")

    if path.name in fresh:
        releases.delete_asset(repo=repo, asset=fresh[path.name])

    command.gh(
        "api",
        "-X",
        "PATCH",
        f"repos/{repo}/releases/assets/{fresh[temp.name].id}",
        "-f",
        f"name={path.name}",
    )

    return digest
