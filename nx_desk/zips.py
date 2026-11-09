import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import IO, Dict, List, Optional, Set, Tuple

from .config import CHUNK, DEFAULT_COMPRESSION, JUNK_NAMES, MAX_UNPACKED, TITLE_ID

# What a zip member stores as its modification time.
DateTime = Tuple[int, int, int, int, int, int]


def plan_repack(infos: List[zipfile.ZipInfo], title_id: str) -> Dict[str, zipfile.ZipInfo]:
    # Every title stays: a pack's extra titles, such as a system font, belong to the game.
    if not TITLE_ID.match(string=title_id):
        raise RuntimeError(f"invalid title id: {title_id!r}")

    plan: Dict[str, zipfile.ZipInfo] = {}
    total = 0
    found = False

    for info in infos:
        name = info.filename.replace("\\", "/")

        if name.endswith("/"):
            continue

        parts = [part for part in name.split(sep="/") if part]

        if ".." in parts or "." in parts or name.startswith("/"):
            raise RuntimeError(f"unsafe path in zip: {name}")

        if parts[0] == "__MACOSX" or parts[-1].lower() in JUNK_NAMES:
            continue

        index = next((i for i, part in enumerate(iterable=parts) if TITLE_ID.match(string=part)), None)

        if index is None:
            continue

        if index + 1 == len(parts):
            raise RuntimeError(f"unexpected structure in zip: {name}")

        ours = parts[index].lower() == title_id.lower()
        found = found or ours
        arcname = "/".join(
            [
                "contents",
                title_id if ours else parts[index].upper(),
                *parts[index + 1 :],
            ],
        )

        if arcname.lower() in {key.lower() for key in plan}:
            raise RuntimeError(f"duplicate file name in zip: {arcname}")

        plan[arcname] = info
        total += info.file_size

    if not found:
        raise RuntimeError(f"no files in {title_id}")

    if total > MAX_UNPACKED:
        raise RuntimeError("unpacked zip is too large")

    return plan


def member_info(
    name: str,
    date_time: DateTime,
    mode: int,
    compress_type: int,
    level: Optional[int] = DEFAULT_COMPRESSION,
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=date_time)
    info.create_system = 3
    info.external_attr = mode << 16
    info.compress_type = compress_type

    if compress_type == zipfile.ZIP_DEFLATED:
        info._compresslevel = level  # type: ignore[attr-defined]

    return info


def add_member(
    output: zipfile.ZipFile,
    arcname: str,
    date_time: DateTime,
    size: int,
    reader: IO[bytes],
    written: Set[str],
) -> None:
    folders = arcname.split(sep="/")[:-1]

    for depth in range(1, len(folders) + 1):
        folder = "/".join(folders[:depth]) + "/"

        if folder not in written:
            written.add(folder)
            output.writestr(
                zinfo_or_arcname=member_info(
                    name=folder,
                    date_time=date_time,
                    mode=0o40755,
                    compress_type=zipfile.ZIP_STORED,
                ),
                data=b"",
            )

    info = member_info(
        name=arcname,
        date_time=date_time,
        mode=0o100644,
        compress_type=output.compression,
        level=output.compresslevel,
    )
    info.file_size = size

    with output.open(name=info, mode="w") as writer:
        shutil.copyfileobj(fsrc=reader, fdst=writer, length=CHUNK)


def repack(
    source: Path,
    target: Path,
    title_id: str,
    cancel: Optional[threading.Event] = None,
    level: int = DEFAULT_COMPRESSION,
) -> None:
    # Members are streamed, never extracted to disk.
    temp = target.with_name(name=target.name + ".tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    method = zipfile.ZIP_DEFLATED if level else zipfile.ZIP_STORED

    try:
        with (
            zipfile.ZipFile(file=source) as original,
            zipfile.ZipFile(file=temp, mode="w", compression=method, compresslevel=level) as output,
        ):
            plan = plan_repack(infos=original.infolist(), title_id=title_id)
            written: Set[str] = set()

            for arcname, member in plan.items():
                if cancel is not None and cancel.is_set():
                    raise Cancelled

                with original.open(name=member) as reader:
                    add_member(
                        output=output,
                        arcname=arcname,
                        date_time=member.date_time,
                        size=member.file_size,
                        reader=reader,
                        written=written,
                    )

            expected = {name: member.CRC for name, member in plan.items()}

        with zipfile.ZipFile(file=temp) as result:
            actual = {i.filename: i.CRC for i in result.infolist() if not i.is_dir()}

            if actual != expected or result.testzip() is not None:
                raise RuntimeError("repacked zip does not match the original")

        os.replace(src=temp, dst=target)

    finally:
        temp.unlink(missing_ok=True)


class Cancelled(Exception):
    pass
