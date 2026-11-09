from typing import Dict

from ..schemas.sizes import SizeScale

BINARY = "binary"
SIZE_UNITS: Dict[str, SizeScale] = {
    BINARY: SizeScale(base=1024, kilo="KiB", mega="MiB", giga="GiB"),
    "decimal": SizeScale(base=1000, kilo="KB", mega="MB", giga="GB"),
}
size_units = BINARY


def set_size_units(units: str) -> None:
    global size_units
    size_units = units if units in SIZE_UNITS else BINARY


def format_size(value: float) -> str:
    scale = SIZE_UNITS[size_units]

    if value >= scale.base**3:
        return f"{value / scale.base**3:.2f} {scale.giga}"

    if value >= scale.base**2:
        return f"{value / scale.base**2:.1f} {scale.mega}"

    return f"{max(1, round(number=value / scale.base))} {scale.kilo}"
