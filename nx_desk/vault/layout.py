import json
import os
from pathlib import Path

from ..config import (
    ART_LOOKUPS_FILE,
    CACHE_DIR,
    CATALOG_FILE,
    CATALOGS_DIR,
    NO_CATALOG,
    PORTS_FILE,
    RELEASE_FILE,
    SETTINGS_FILE,
    STATE_FILE,
    TITLE_IDS_FILE,
)
from ..names import art_name, art_stem_of

# The files of the first layout, in .catalogs/, and where each one lives now.
OLD_SETTINGS = "index.json"
OLD_CACHES = {"_title_ids.json": TITLE_IDS_FILE, "_ports.json": PORTS_FILE, "_steamgriddb.json": ART_LOOKUPS_FILE}
# The ending of a file of one catalog in .catalogs/, and its name in the catalog's own folder; None for the art
# index, which is not kept any more.
OLD_ENDINGS = ((".state.json", STATE_FILE), (".release.json", RELEASE_FILE), (".covers.json", None))


def move(source: Path, target: Path) -> None:
    if source.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src=source, dst=target)


# The art index of the first layout said which URL each file came from. Each file takes a name with its URL's digest
# instead, which is what the app looks for now, so no image is fetched again.
def rename_art(index: Path, art_dir: Path) -> None:
    try:
        saved = json.loads(s=index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}

    for name, url in saved.items() if isinstance(saved, dict) else ():
        if not isinstance(name, str) or not isinstance(url, str) or not url or Path(name).name != name:
            continue

        source, target = art_dir / name, art_dir / art_name(stem=art_stem_of(file_name=name), url=url)

        if source.is_file() and not target.exists():
            os.replace(src=source, dst=target)

    index.unlink(missing_ok=True)


def split(name: str) -> tuple[str, str | None] | None:
    # The old settings are not a catalog's file, whether or not they have moved.
    if name == OLD_SETTINGS:
        return None

    for ending, new_name in OLD_ENDINGS:
        if name.endswith(ending):
            return name[: -len(ending)], new_name

    if name.endswith(".json") and not name.startswith("_"):
        return name[: -len(".json")], CATALOG_FILE

    return None


# Brings a data folder made by an older version to the layout this one reads: settings.json at the top, the caches in
# cache/, the files of each catalog in a folder of its own, and art files named after their URL. It only moves
# files that are not already in place, so it can run on every start and finish what an interrupted run left.
def migrate_layout(base: Path) -> None:
    catalogs = base / CATALOGS_DIR

    if not catalogs.is_dir():
        return

    steps = [(catalogs / OLD_SETTINGS, base / SETTINGS_FILE)]
    steps += [(catalogs / old, base / CACHE_DIR / new) for old, new in OLD_CACHES.items()]

    for source, target in steps:
        try:
            move(source=source, target=target)
        except OSError:
            continue

    for path in sorted(catalogs.glob(pattern="*.json")):
        parts = split(name=path.name)

        try:
            if parts is None:
                continue

            folder, new_name = parts

            if folder == NO_CATALOG:
                path.unlink(missing_ok=True)
            elif new_name is None:
                rename_art(index=path, art_dir=base / "covers" / folder)
            else:
                move(source=path, target=catalogs / folder / new_name)
        except OSError:
            continue

    # The first versions made these for a catalog that was not there, and never put anything in them.
    for leftover in (base / "covers" / NO_CATALOG,):
        try:
            leftover.rmdir()
        except OSError:
            pass
