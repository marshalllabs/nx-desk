import http.client
import socket
import ssl
import sys
import urllib.error
import urllib.request

from .config import user_agent


def ssl_context() -> ssl.SSLContext | None:
    # System CA paths differ between distros, so packaged builds carry their own.
    if not getattr(sys, "frozen", False):
        return None

    import certifi

    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = ssl_context()
USER_AGENT = user_agent()


def http_get(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> http.client.HTTPResponse:
    request = urllib.request.Request(url=url, headers={"User-Agent": USER_AGENT, **(headers or {})})

    return urllib.request.urlopen(url=request, timeout=timeout, context=SSL_CONTEXT)


# A read waiting on a slow server only wakes up once its socket is shut down. Closing the
# response from another thread is not safe, so the socket is shut and the reader closes it.
def abort(response: http.client.HTTPResponse) -> None:
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)

    if isinstance(sock, socket.socket):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
