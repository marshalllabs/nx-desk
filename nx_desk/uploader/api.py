import http.client
from contextlib import contextmanager
from typing import Iterator, List, Optional
from urllib.parse import urlsplit

from pydantic import BaseModel, JsonValue, TypeAdapter

from .. import net
from ..config import user_agent
from ..utils.json import parse_json
from . import command

API_HOST = "api.github.com"
API_VERSION = "2026-03-10"
TIMEOUT = 30
MAX_JSON = 8 * 1024 * 1024
ROWS: TypeAdapter[List[JsonValue]] = TypeAdapter(type=List[JsonValue])


def endpoint(path: str) -> str:
    if path.startswith(("/", "http:", "https:")) or "\\" in path or "#" in path:
        raise ValueError("GitHub API paths must be relative")

    return f"https://{API_HOST}/{path}"


@contextmanager
def response(
    url: str,
    method: str = "GET",
    data: Optional[BaseModel] = None,
    accept: str = "application/vnd.github+json",
) -> Iterator[http.client.HTTPResponse]:
    parts = urlsplit(url=url)

    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
    ):
        raise command.GitHubError("GitHub requests require a valid HTTPS URL")

    headers = {"User-Agent": user_agent(), "Accept": accept}

    # Signed asset redirects go to storage hosts; never forward the PAT to them.
    if parts.hostname == API_HOST:
        headers["Authorization"] = f"Bearer {command.token()}"
        headers["X-GitHub-Api-Version"] = API_VERSION

    body = None

    if data is not None:
        body = data.model_dump_json(exclude_none=True).encode(encoding="utf-8")
        headers["Content-Type"] = "application/json"

    connection = http.client.HTTPSConnection(host=parts.hostname, timeout=TIMEOUT, context=net.SSL_CONTEXT)

    try:
        with command.interruptible(connection=connection):
            command.stop_point()
            connection.request(
                method=method,
                url=parts.path + (f"?{parts.query}" if parts.query else ""),
                body=body,
                headers=headers,
            )
            reply = connection.getresponse()

            try:
                with command.interruptible(connection=connection, reply=reply):
                    yield reply

            finally:
                reply.close()

    except (OSError, http.client.HTTPException) as error:
        command.stop_point()

        raise command.NetworkError("GitHub connection interrupted; try again.") from error

    finally:
        connection.close()


def check(reply: http.client.HTTPResponse) -> None:
    if 200 <= reply.status < 300:
        return

    messages = {
        401: "Token is invalid or expired; replace it in Settings > GitHub.",
        403: "Token access was refused; check repository permissions and organization approval.",
        404: "Resource not found or the token cannot access it.",
        422: "GitHub rejected the change; check the release tag or asset name.",
    }
    message = messages.get(reply.status, "GitHub refused the request.")
    # Read only enough to recognize throttling; server messages can echo request data.
    body = reply.read(65536)

    if reply.status == 429 or (
        reply.status == 403
        and (
            reply.getheader("X-RateLimit-Remaining") == "0"
            or b"rate limit" in body.lower()
            or reply.getheader("Retry-After")
        )
    ):
        message = "GitHub rate limit reached."

    raise command.GitHubError(f"HTTP {reply.status}: {message}", status=reply.status)


def request(path: str, method: str = "GET", data: Optional[BaseModel] = None) -> JsonValue:
    rate, server = iter(command.RATE_WAITS), iter(command.SERVER_WAITS)

    while True:
        try:
            with response(url=endpoint(path=path), method=method, data=data) as reply:
                check(reply=reply)
                body = reply.read(MAX_JSON + 1)

                if len(body) > MAX_JSON:
                    raise command.GitHubError("GitHub API response is too large")

                try:
                    return parse_json(text=body.decode(encoding="utf-8")) if body else None

                except (ValueError, UnicodeError) as error:
                    raise command.GitHubError("GitHub returned invalid JSON") from error

        except command.GitHubError as error:
            if command.RATE_LIMITED.search(string=str(error)):
                wait = next(rate, None)

            elif (
                isinstance(error, command.NetworkError) or error.status in (500, 502, 503, 504)
            ) and method in command.REPEATABLE:
                wait = next(server, None)

            else:
                wait = None

            if wait is None:
                raise

            command.pause(seconds=wait)


def pages(path: str) -> List[JsonValue]:
    rows: List[JsonValue] = []
    page = 1

    while True:
        separator = "&" if "?" in path else "?"
        batch = ROWS.validate_python(request(path=f"{path}{separator}per_page=100&page={page}"))
        rows.extend(batch)

        if len(batch) < 100:
            return rows

        page += 1
