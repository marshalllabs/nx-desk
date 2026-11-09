import re
import shutil
import subprocess
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

from ..system import system_env
from ..zips import Cancelled

# GitHub limits how fast content is created and asks callers to wait; seconds between tries.
RATE_WAITS = (60, 120, 240)
RATE_LIMITED = re.compile(pattern=r"rate limit|HTTP 429", flags=re.IGNORECASE)
# GitHub sometimes fails a request on its side for a moment; seconds between tries.
SERVER_WAITS = (5, 15, 45)
SERVER_ERROR = re.compile(pattern=r"HTTP 50[0234]\b")
# API calls that give the same result when sent twice. Creating things is left out.
REPEATABLE = ("GET", "PATCH", "DELETE")


class GhError(Exception):
    pass


class NetworkError(GhError):
    pass


# The cancel event of the job this thread runs, which lets Stop end a long gh call.
running = threading.local()


@contextmanager
def stoppable(cancel: Optional[threading.Event]) -> Iterator[None]:
    previous = getattr(running, "cancel", None)
    running.cancel = cancel

    try:
        yield

    finally:
        running.cancel = previous


def stop_point() -> None:
    cancel = getattr(running, "cancel", None)

    if cancel is not None and cancel.is_set():
        raise Cancelled


def gh(*args: str) -> str:
    command = shutil.which(cmd="gh")

    if not command:
        raise GhError("GitHub CLI (gh) is not installed. Install gh and try again.")

    rate, server = iter(RATE_WAITS), iter(SERVER_WAITS)

    while True:
        try:
            return run_gh(command=command, args=args)

        except GhError as error:
            # A request refused for its rate was not carried out, so sending it again is safe.
            if RATE_LIMITED.search(string=str(error)):
                wait = next(rate, None)

            elif SERVER_ERROR.search(string=str(error)) and repeatable(args=args):
                wait = next(server, None)

            else:
                wait = None

            if wait is None:
                raise

            pause(seconds=wait)


def repeatable(args: Tuple[str, ...]) -> bool:
    if not args or args[0] != "api":
        return False

    method = args[args.index("-X") + 1] if "-X" in args[:-1] else "GET"

    return method.upper() in REPEATABLE


def pause(seconds: float) -> None:
    cancel = getattr(running, "cancel", None)

    if cancel is None:
        time.sleep(seconds)

    elif cancel.wait(seconds):
        raise Cancelled


def run_gh(command: str, args: Tuple[str, ...]) -> str:
    process = subprocess.Popen(
        args=[command, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=system_env(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    while True:
        try:
            output, errors = process.communicate(timeout=0.2)
            break

        except subprocess.TimeoutExpired:
            try:
                stop_point()

            except Cancelled:
                process.kill()
                process.communicate()
                raise

    if process.returncode:
        raise GhError(errors.strip() or f"gh failed with code {process.returncode}")

    return output


def ensure_login() -> None:
    try:
        gh("auth", "status")

    except GhError as error:
        if "not installed" in str(error):
            raise

        raise GhError("You are not signed in to gh. Run `gh auth login` in a terminal and try again.") from error
