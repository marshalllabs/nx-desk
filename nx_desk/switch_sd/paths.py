import hashlib
import stat
import threading
from pathlib import Path, PurePosixPath
from typing import List

from ..config import CHUNK
from ..zips import Cancelled

MANIFEST = ".nx-desk.json"
MAX_FILES = 100_000
CONTENT_DIRS = {"romfs", "exefs", "cheats"}
CONTENT_IMAGES = {"romfs.bin", "exefs.nsp"}


def stop(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled


def relative_parts(name: str) -> List[str]:
    parts = name.split(sep="/")

    if (
        not name
        or "\\" in name
        or any(
            part in ("", ".", "..")
            or part.split(sep=".")[0].upper()
            in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}
            or ":" in part
            or part.endswith((".", " "))
            or protected(name=part)
            for part in parts
        )
    ):
        raise ValueError("Unsafe or protected path in mod content")

    if PurePosixPath(name).is_absolute():
        raise ValueError("Absolute mod paths are not supported")

    return parts


def protected(name: str) -> bool:
    text = name.casefold()

    return (
        text == ".env"
        or text.startswith((".env.", ".dev.vars"))
        or text
        in {
            ".ssh",
            ".secrets",
            ".credentials",
            "prod.keys",
            "title.keys",
            "secret_key",
            "credentials.json",
            "id_rsa",
            "id_ed25519",
        }
    )


def signature(path: Path) -> List[int]:
    saved = path.lstat()

    if stat.S_ISLNK(saved.st_mode):
        raise ValueError("Symbolic links are not supported on a Switch card")

    return [saved.st_dev, saved.st_ino, saved.st_mtime_ns, saved.st_size]


def safe_path(root: Path, relative: str) -> Path:
    parts = relative_parts(name=relative)
    current = root

    for part in parts:
        if current.is_dir():
            matches = [path for path in current.iterdir() if path.name.casefold() == part.casefold()]

            if len(matches) > 1:
                raise ValueError("Ambiguous filename case in mod content")

            current = matches[0] if matches else current / part

        else:
            current = current / part

        if current.is_symlink():
            raise ValueError("Symbolic links are not supported on a Switch card")

    return current


def tree_files(root: Path, cancel: threading.Event) -> List[Path]:
    result: List[Path] = []
    pending = [root]
    visited = 0

    while pending:
        stop(cancel=cancel)
        folder = pending.pop()

        for path in folder.iterdir():
            visited += 1

            if visited > MAX_FILES:
                raise ValueError("Mod content has too many files or directories")

            relative_parts(name=path.relative_to(root).as_posix())
            mode = path.lstat().st_mode

            if stat.S_ISLNK(mode):
                raise ValueError("Symbolic links are not supported in mod content")

            if stat.S_ISDIR(mode):
                pending.append(path)

            elif stat.S_ISREG(mode):
                result.append(path)

            else:
                raise ValueError("Special files are not supported in mod content")

    return sorted(result)


def digest(path: Path, cancel: threading.Event) -> str:
    hashed = hashlib.sha256()

    with path.open(mode="rb") as reader:
        while block := reader.read(CHUNK):
            stop(cancel=cancel)
            hashed.update(block)

    return hashed.hexdigest()
