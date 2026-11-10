from typing import List, Optional

from ..schemas.switch_sd import MountedVolume, SwitchCard
from .paths import safe_path, signature

FILESYSTEMS = {"vfat", "fat", "fat32", "exfat", "msdos", "msdosfs"}
MARKERS = ("atmosphere/package3", "bootloader/hekate_ipl.ini", "emuMMC/emummc.ini")


def detect(volume: MountedVolume) -> Optional[SwitchCard]:
    if volume.filesystem.casefold() not in FILESYSTEMS or not volume.root.is_absolute() or volume.root.is_symlink():
        return None

    root = volume.root

    try:
        atmosphere = safe_path(root=root, relative="atmosphere")

        if not atmosphere.is_dir():
            return None

        markers = [name for name in MARKERS if safe_path(root=root, relative=name).is_file()]

        if "atmosphere/package3" not in markers and not (
            safe_path(root=root, relative="atmosphere/contents").is_dir() and markers
        ):
            return None

        identity = signature(path=root)[:2] + signature(path=atmosphere)[:2]

        for name in markers:
            identity.extend(signature(path=root / name))

        return SwitchCard(
            root=volume.root,
            label=volume.label,
            filesystem=volume.filesystem,
            device=volume.device,
            read_only=volume.read_only,
            markers=markers,
            identity=identity,
        )

    except (OSError, ValueError):
        return None


def discover(volumes: List[MountedVolume]) -> List[SwitchCard]:
    cards = [card for volume in volumes if (card := detect(volume=volume)) is not None]

    return sorted({str(card.root): card for card in cards}.values(), key=lambda card: str(card.root))


def require(card: SwitchCard) -> None:
    current = detect(volume=card)

    if current is None or current.identity != card.identity:
        raise ValueError("The selected card was disconnected or changed. Scan and choose it again.")
