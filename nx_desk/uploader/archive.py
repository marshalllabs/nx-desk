import re
import shutil
import unicodedata
import zipfile
from pathlib import Path
from typing import List

from ..schemas.common import Progress
from ..utils.callbacks import quiet
from ..utils.files import free_path
from . import command

# GitHub's limit is 2 GiB per file. This stays clearly below it.
PART_SIZE = 2_000_000_000
TEMP_PREFIX = "uploading-"
ZIP_VERSION = re.compile(pattern=r"^\[([^\]]+)\]")
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
BLOCK = 1024 * 1024


# GitHub rewrites spaces and brackets in asset names, so names are made safe up front.
def asset_stem(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    text = text.encode(encoding="ascii", errors="ignore").decode(encoding="ascii")

    return re.sub(pattern=r"[^A-Za-z0-9]+", repl="-", string=text).strip("-") or "folder"


# The zip's own version, such as 1.1.0-v65536, so the release shows what each file is.
def folder_version(folder: Path) -> str:
    names = [path.name for path in folder.iterdir() if path.suffix.lower() == ".zip"]
    found = [match.group(1) for match in map(ZIP_VERSION.match, sorted(names)) if match]

    return re.sub(pattern=r"[^A-Za-z0-9._-]+", repl="-", string=found[-1]).strip("-.") if found else ""


def asset_base(folder: Path) -> str:
    version = folder_version(folder=folder)

    return f"{asset_stem(name=folder.name)}-{version}" if version else asset_stem(name=folder.name)


def archive_name(path: Path, folder: Path) -> str:
    return unicodedata.normalize("NFC", (Path(folder.name) / path.relative_to(folder)).as_posix())


# Fixed dates, order and modes make the same files give the same bytes on any system, so an
# unchanged folder has the same hash as its copy on the release. Mods are already compressed.
def build_zip(folder: Path, target: Path, moved: Progress = quiet) -> None:
    done = 0
    paths = [path for path in folder.rglob(pattern="*") if not path.is_symlink()]

    with zipfile.ZipFile(file=target, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as output:
        for path in sorted(paths, key=lambda item: archive_name(path=item, folder=folder)):
            name = archive_name(path=path, folder=folder)
            info = zipfile.ZipInfo(filename=name + "/" if path.is_dir() else name, date_time=FIXED_DATE)
            info.create_system = 3
            info.external_attr = (0o40755 if path.is_dir() else 0o100644) << 16

            if path.is_dir():
                output.writestr(zinfo_or_arcname=info, data=b"")
                continue

            with open(file=path, mode="rb") as reader, output.open(name=info, mode="w", force_zip64=True) as writer:
                for block in iter(lambda: reader.read(BLOCK), b""):
                    command.stop_point()
                    writer.write(block)
                    done += len(block)
                    moved(done)


def split_file(path: Path, part_size: int, moved: Progress = quiet) -> List[Path]:
    if path.stat().st_size <= part_size:
        return [path]

    parts: List[Path] = []
    done = 0

    with open(file=path, mode="rb") as reader:
        while True:
            part = path.with_name(name=f"{path.name}.{len(parts) + 1:03d}")
            written = 0

            with open(file=part, mode="wb") as writer:
                while written < part_size:
                    command.stop_point()
                    block = reader.read(min(BLOCK, part_size - written))

                    if not block:
                        break

                    writer.write(block)
                    written += len(block)
                    done += len(block)
                    moved(done)

            if not written:
                part.unlink()
                break

            parts.append(part)

    path.unlink()

    return parts


# Every upload holds one folder. A folder of the same name stays, the new one gets a number.
def extract_folder(archive: Path, root: Path, place: Path) -> str:
    with zipfile.ZipFile(file=archive) as source:
        tops = {name.split(sep="/")[0] for name in source.namelist()}

        if len(tops) != 1 or not next(iter(tops)) or ".." in tops:
            raise command.GhError("zip does not contain exactly one top folder")

        top = next(iter(tops))
        source.extractall(path=place / "out")

    target = free_path(path=root / top)
    shutil.move(src=str(place / "out" / top), dst=str(target))

    return target.name
