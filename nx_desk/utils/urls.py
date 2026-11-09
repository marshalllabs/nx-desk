def https_or_empty(value: object) -> str:
    if isinstance(value, str) and value.startswith("https://"):
        return value

    return ""
