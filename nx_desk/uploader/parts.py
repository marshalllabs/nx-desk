import functools
import re
import shutil
from pathlib import Path
from typing import Collection, Dict, Iterable, List

from ..schemas.common import Progress, Report
from ..schemas.github import Asset, UploadPart
from ..utils.callbacks import offset, quiet
from ..utils.files import sha256_of
from ..utils.sizes import format_size
from . import archive, command, download, progress, releases, upload

PART_SUFFIX = re.compile(pattern=r"\.\d{3}$")


# Files of one folder whatever version they carry, so a new version replaces the old file.
def owned_assets(stem: str, assets: Dict[str, Asset]) -> Dict[str, Asset]:
    pattern = re.compile(
        pattern=rf"^{re.escape(pattern=stem)}(-(v?\d|miss)[A-Za-z0-9._-]*)?\.zip(\.\d{{3}})?$",
        flags=re.IGNORECASE,
    )

    return {name: asset for name, asset in assets.items() if pattern.match(string=name)}


# One folder may be several parts on the release, and a part alone is useless.
def with_sibling_parts(names: Collection[str], all_names: Iterable[str]) -> List[str]:
    stems = {PART_SUFFIX.sub(repl="", string=name) for name in names}

    return [name for name in all_names if name in names or PART_SUFFIX.sub(repl="", string=name) in stems]


def group_key(name: str) -> str:
    return PART_SUFFIX.sub(repl="", string=name)


# Release files as the panels count them: the parts of a split zip make one.
def games_text(assets: Iterable[Asset]) -> str:
    count = len({group_key(name=asset.name) for asset in assets})

    return f"{count} game" if count == 1 else f"{count} games"


def download_group(
    repo: str,
    tag: str,
    names: List[str],
    assets: Dict[str, Asset],
    place: Path,
    report: Report = quiet,
    moved: Progress = quiet,
) -> Path:
    before = 0

    for index, name in enumerate(iterable=names, start=1):
        size = assets[name].size or 0
        report(f"downloading {name} ({format_size(value=size)}, {index}/{len(names)})")
        progress.transfer(
            action=functools.partial(
                download.asset,
                repo=repo,
                asset_id=assets[name].id,
                target=place / name,
                moved=offset(moved=moved, before=before),
            ),
            report=report,
            name=name,
            partial=place / name,
        )

        before += size
        moved(before)
        digest = assets[name].digest

        if digest and digest != f"sha256:{sha256_of(path=place / name)}":
            raise command.GitHubError(f"{name}: downloaded file does not match SHA-256")

        report(f"{name}: SHA-256 matches GitHub" if digest else f"{name}: GitHub gave no SHA-256 to check")

    target = place / group_key(name=names[0])

    if len(names) > 1 or names[0] != target.name:
        report(f"joining {len(names)} parts into {target.name}")

        with open(file=target, mode="wb") as output:
            for name in sorted(names):
                with open(file=place / name, mode="rb") as reader:
                    shutil.copyfileobj(fsrc=reader, fdst=output, length=archive.BLOCK)

                (place / name).unlink()

    return target


# New files go up under a temporary name and are checked before the old ones are removed,
# so a failed upload leaves the old copy in place.
# The label keeps the folder's real name, which the file name cannot, for showing it grouped by game.
def upload_parts(
    repo: str,
    tag: str,
    stem: str,
    parts: List[Path],
    assets: Dict[str, Asset],
    report: Report = quiet,
    label: str = "",
    moved: Progress = quiet,
) -> None:
    uploads: List[UploadPart] = []
    before = 0

    for index, part in enumerate(iterable=parts, start=1):
        temp = part.with_name(name=archive.TEMP_PREFIX + part.name)
        part.rename(target=temp)
        size = temp.stat().st_size
        report(f"uploading {part.name} ({format_size(value=size)}, {index}/{len(parts)})")
        upload.upload_file(
            repo=repo,
            tag=tag,
            path=temp,
            report=report,
            name=part.name,
            moved=offset(moved=moved, before=before),
        )
        before += size
        uploads.append(UploadPart(name=part.name, path=temp))

    report("checking SHA-256 of the files on GitHub")
    fresh = releases.remote_assets(repo=repo, tag=tag)

    for upload_part in uploads:
        name, temp = upload_part.name, upload_part.path

        if fresh[temp.name].digest != f"sha256:{sha256_of(path=temp)}":
            raise command.GitHubError(f"{name}: file on GitHub does not match, the old copy is kept")

    command.stop_point()
    old = owned_assets(stem=stem, assets=assets)

    if old:
        report(f"removing the old {'file' if len(old) == 1 else 'files'}: {', '.join(sorted(old))}")

    # Stopping between these calls would leave the release without either copy.
    with command.stoppable(cancel=None):
        for asset in old.values():
            releases.delete_asset(repo=repo, asset=asset)

        for upload_part in uploads:
            name, temp = upload_part.name, upload_part.path
            releases.rename_asset(repo=repo, asset=fresh[temp.name], name=name, label=label)

    report(f"named {', '.join(part.name for part in uploads)} on GitHub" + (f", labelled {label}" if label else ""))
