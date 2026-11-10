import http.client
import re
import socket
import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from .. import net
from ..zips import Cancelled

RATE_WAITS = (60, 120, 240)
RATE_LIMITED = re.compile(pattern=r"rate limit|HTTP 429", flags=re.IGNORECASE)
SERVER_WAITS = (5, 15, 45)
REPEATABLE = ("GET", "PATCH", "DELETE")


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status


class NetworkError(GitHubError):
    pass


running = threading.local()


def authenticate(provider: Callable[[], str]) -> None:
    running.provider = provider


def token() -> str:
    provider: Callable[[], str] = getattr(running, "provider", lambda: "")
    value = provider()

    if not value:
        raise GitHubError("Add a GitHub personal access token in Settings > GitHub.")

    return value


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


@contextmanager
def interruptible(
    connection: http.client.HTTPSConnection,
    reply: Optional[http.client.HTTPResponse] = None,
) -> Iterator[None]:
    cancel = getattr(running, "cancel", None)
    finished = threading.Event()

    def watch() -> None:
        while not finished.wait(timeout=0.1):
            if cancel is not None and cancel.is_set():
                sock = connection.sock

                if isinstance(sock, socket.socket):
                    try:
                        sock.shutdown(socket.SHUT_RDWR)

                    except OSError:
                        pass

                    return

                if reply is not None:
                    net.abort(response=reply)

                    return

    if cancel is not None:
        threading.Thread(target=watch, daemon=True).start()

    try:
        stop_point()
        yield

    finally:
        finished.set()


def pause(seconds: float) -> None:
    cancel = getattr(running, "cancel", None)

    if cancel is None:
        time.sleep(seconds)

    elif cancel.wait(seconds):
        raise Cancelled
