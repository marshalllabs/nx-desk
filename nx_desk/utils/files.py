import hashlib
from pathlib import Path


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()

    with open(file=path, mode="rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def tree_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size

    return sum(item.stat().st_size for item in path.rglob(pattern="*") if item.is_file() and not item.is_symlink())


# The path itself when it is free, else the first free "<name> (2)", "<name> (3)", ...
def free_path(path: Path) -> Path:
    candidate, number = path, 2

    while candidate.exists():
        candidate, number = path.with_name(name=f"{path.name} ({number})"), number + 1

    return candidate
