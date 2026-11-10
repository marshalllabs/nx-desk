import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

from ..config import TITLE_ID
from ..schemas.switch_sd import SDContentIdentity, SDManifest, SDTitle, SwitchCard
from . import detect
from .paths import CONTENT_DIRS, CONTENT_IMAGES, MANIFEST, digest, safe_path, stop, tree_files


def manifest(folder: Path) -> Optional[SDManifest]:
    path = safe_path(root=folder, relative=MANIFEST)

    if not path.is_file():
        return None

    with path.open(mode="rb") as reader:
        data = reader.read(1024 * 1024 + 1)

    if len(data) > 1024 * 1024:
        raise ValueError("NX Desk metadata is too large")

    saved = SDManifest.model_validate_json(json_data=data)

    for name, checksum in saved.files.items():
        safe_path(root=folder, relative=name)

        if name == MANIFEST or not re.fullmatch(pattern=r"[0-9a-f]{64}", string=checksum):
            raise ValueError("Invalid NX Desk metadata")

    return saved


def relabel(rows: List[SDTitle], names: Dict[str, SDContentIdentity]) -> List[SDTitle]:
    result: List[SDTitle] = []

    for row in rows:
        identity = names.get(row.title_id, SDContentIdentity())
        result.append(row.model_copy(update={"name": identity.name, "category": identity.category}))

    return result


def title(folder: Path, names: Dict[str, SDContentIdentity], cancel: threading.Event) -> SDTitle:
    title_id = folder.name.upper()
    identity = names.get(title_id, SDContentIdentity())
    kinds = [name for name in sorted(CONTENT_DIRS) if safe_path(root=folder, relative=name).is_dir()]
    kinds.extend(name for name in sorted(CONTENT_IMAGES) if safe_path(root=folder, relative=name).is_file())

    files = [path for path in tree_files(root=folder, cancel=cancel) if path.parent != folder or path.name != MANIFEST]
    row = SDTitle(
        title_id=title_id,
        name=identity.name,
        category=identity.category,
        kinds=kinds,
        size=sum(path.stat().st_size for path in files),
        files=len(files),
    )

    try:
        saved = manifest(folder=folder)

        if saved is None:
            return row

        expected = {path.relative_to(folder).as_posix() for path in files}

        if not saved.files or set(saved.files) != expected or not saved.packages:
            row.status = "Mixed / modified"

            return row

        for name, checksum in saved.files.items():
            stop(cancel=cancel)

            if digest(path=safe_path(root=folder, relative=name), cancel=cancel) != checksum:
                row.status = "Mixed / modified"

                return row

        row.status = "Verified copy"
        row.mod_version = ", ".join(sorted({item.mod_version for item in saved.packages if item.mod_version}))
        row.target_game = ", ".join(sorted({item.game_version for item in saved.packages if item.game_version}))

    except (OSError, ValueError):
        row.status = "Invalid metadata"

    return row


def scan(card: SwitchCard, names: Dict[str, SDContentIdentity], cancel: threading.Event) -> List[SDTitle]:
    detect.require(card=card)
    root = safe_path(root=card.root, relative="atmosphere/contents")

    if not root.exists():
        return []

    result: List[SDTitle] = []

    for folder in sorted(root.iterdir()):
        stop(cancel=cancel)

        if not TITLE_ID.fullmatch(string=folder.name):
            continue

        try:
            if folder.is_symlink() or not folder.is_dir():
                raise ValueError("Unsafe title directory")

            result.append(title(folder=folder, names=names, cancel=cancel))

        except (OSError, ValueError):
            identity = names.get(folder.name.upper(), SDContentIdentity())
            result.append(
                SDTitle(
                    title_id=folder.name.upper(),
                    name=identity.name,
                    category=identity.category,
                    kinds=[],
                    size=0,
                    files=0,
                    status="Unreadable / unsafe",
                ),
            )

    detect.require(card=card)

    return result
