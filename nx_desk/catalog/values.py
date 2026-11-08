import re
from typing import Any

from ..config import GDRIVE_URL, SAFE_GDRIVE
from .fields import FIELD_ALIASES


def https_or_empty(value: object) -> str:
    if isinstance(value, str) and value.startswith("https://"):
        return value

    return ""


def dig(obj: object, path: str) -> Any:
    for part in str(path).split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list) and part.lstrip("-").isdigit() and -len(obj) <= int(part) < len(obj):
            obj = obj[int(part)]
        else:
            return None

        if obj is None:
            return None

    return obj


def pick(raw: object, field: str, mapping: dict[str, str] | None) -> Any:
    if mapping and mapping.get(field):
        return dig(obj=raw, path=mapping[field])

    for alias in FIELD_ALIASES.get(field, [field]):
        value = dig(obj=raw, path=alias)

        if value is not None:
            return value

    return None


def as_text(value: object) -> str:
    return str(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def as_size(value: object) -> int:
    if isinstance(value, bool):
        return 0

    if isinstance(value, int):
        return value

    if isinstance(value, float) and value.is_integer():
        return int(value)

    if isinstance(value, str):
        text = re.sub(pattern=r"[,\s_]", repl="", string=value)

        if text.isdigit():
            return int(text)

    return 0


def clean_mapping(mapping: object) -> dict[str, str]:
    if not isinstance(mapping, dict):
        return {}

    return {field: key.strip() for field, key in mapping.items() if isinstance(key, str) and key.strip()}


def resolve_urls(primary: object, mirrors: object) -> list[str]:
    urls = [https_or_empty(value=primary)]

    for mirror in as_list(value=mirrors):
        if isinstance(mirror, str) and mirror.startswith("gdrive:"):
            file_id = mirror[len("gdrive:") :]

            if SAFE_GDRIVE.match(string=file_id):
                urls.append(GDRIVE_URL + file_id)
        else:
            urls.append(https_or_empty(value=mirror))

    return [url for url in dict.fromkeys(urls) if url]
