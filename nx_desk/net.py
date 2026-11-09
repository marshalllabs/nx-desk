import http.client
import socket
import ssl
import sys
import urllib.error
import urllib.request
from typing import Dict, Optional
from urllib.parse import urlsplit

from .config import user_agent


def ssl_context() -> Optional[ssl.SSLContext]:
    # System CA paths differ between distros, so packaged builds carry their own.
    if not getattr(sys, "frozen", False):
        return None

    import certifi

    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = ssl_context()


def http_get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> http.client.HTTPResponse:
    if urlsplit(url=url).scheme not in ("http", "https"):
        raise ValueError("HTTP requests require an HTTP or HTTPS URL")

    request = urllib.request.Request(url=url, headers={"User-Agent": user_agent(), **(headers or {})})

    response = urllib.request.urlopen(url=request, timeout=timeout, context=SSL_CONTEXT)

    if not isinstance(response, http.client.HTTPResponse):
        response.close()
        raise TypeError("HTTP requests must return an HTTP response")

    return response


# A read waiting on a slow server only wakes up once its socket is shut down. Closing the
# response from another thread is not safe, so the socket is shut and the reader closes it.
def abort(response: http.client.HTTPResponse) -> None:
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)

    if isinstance(sock, socket.socket):
        try:
            sock.shutdown(socket.SHUT_RDWR)

        except OSError:
            pass
