import re


# The full size from a Content-Range header such as "bytes 0-99/1000"; 0 when it is missing.
def content_range_total(value: str | None) -> int:
    match = re.search(pattern=r"/(\d+)$", string=value or "")

    return int(match.group(1)) if match else 0


# The seconds a Retry-After header asks for; 0 when it is missing, a date or out of range.
def retry_after(value: str | None) -> int:
    try:
        seconds = int(str(value or "").strip())
    except ValueError:
        return 0

    return max(0, min(seconds, 3600))
