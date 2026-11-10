from pathlib import Path
from typing import List

from PySide6.QtCore import QStorageInfo

from ...schemas.switch_sd import MountedVolume
from ...switch_sd.detect import FILESYSTEMS


def mounted_volumes() -> List[MountedVolume]:
    result: List[MountedVolume] = []

    for volume in QStorageInfo.mountedVolumes():
        filesystem = bytes(volume.fileSystemType().data()).decode(encoding="ascii", errors="replace").casefold()

        if not volume.isValid() or not volume.isReady() or filesystem not in FILESYSTEMS:
            continue

        result.append(
            MountedVolume(
                root=Path(volume.rootPath()),
                label=volume.displayName(),
                filesystem=filesystem,
                device=bytes(volume.device().data()).hex(),
                read_only=volume.isReadOnly(),
            ),
        )

    return result
