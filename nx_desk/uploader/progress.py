import re
import threading
from pathlib import Path
from typing import Callable, Optional

from ..schemas.common import Progress, Report
from . import command

# A big transfer can lose its connection; seconds between tries.
NETWORK_WAITS = (5, 15, 30)
NETWORK_TROUBLE = re.compile(
    pattern=r"connection reset|connection refused|broken pipe|timed? ?out|\bEOF\b|TLS handshake|stream error|HTTP 50[0-4]|"
    r"name resolution",
    flags=re.IGNORECASE,
)


# Sends or fetches one file, which is safe to repeat from the start.
def transfer[T](action: Callable[[], T], report: Report, name: str, partial: Optional[Path] = None) -> T:
    network, rate = iter(NETWORK_WAITS), iter(command.RATE_WAITS)

    while True:
        try:
            return action()

        except command.GhError as error:
            limited = command.RATE_LIMITED.search(string=str(error))
            lost = isinstance(error, command.NetworkError) or NETWORK_TROUBLE.search(string=str(error))
            wait = next(rate if limited else network, None) if limited or lost else None

            if wait is None:
                raise

            reason = "GitHub asked to slow down" if limited else "connection lost"
            report(f"{name}: {reason}, trying again in {wait}s ({error})")
            command.pause(seconds=wait)

            if partial is not None:
                partial.unlink(missing_ok=True)


# The file grows in the target folder while gh fetches it, which is the only sign of progress.
def watch_file(path: Path, moved: Progress) -> threading.Event:
    finished = threading.Event()

    def watch() -> None:
        while not finished.wait(timeout=0.5):
            try:
                moved(path.stat().st_size)

            except OSError:
                pass

    threading.Thread(target=watch, daemon=True).start()

    return finished
