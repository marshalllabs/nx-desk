import http.client
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote, urlencode

from .. import net
from ..config import user_agent
from ..schemas.common import Progress, Report
from ..utils.callbacks import quiet
from . import command, progress, releases

UPLOAD_HOST = "uploads.github.com"
UPLOAD_BLOCK = 256 * 1024
UPLOAD_TIMEOUT = 120
USER_AGENT = user_agent()


# gh reports nothing while it uploads, so the file is sent here, in pieces that can be counted.
# The token stays in memory and goes only to GitHub's upload host.
def post_asset(repo: str, release: int, path: Path, token: str, moved: Progress) -> None:
    connection = http.client.HTTPSConnection(host=UPLOAD_HOST, timeout=UPLOAD_TIMEOUT, context=net.SSL_CONTEXT)
    query = urlencode(query={"name": path.name})

    try:
        connection.putrequest(method="POST", url=f"/repos/{quote(string=repo)}/releases/{release}/assets?{query}")

        for key, value in (
            ("Authorization", f"Bearer {token}"),
            ("Accept", "application/vnd.github+json"),
            ("User-Agent", USER_AGENT),
            ("Content-Type", mimetypes.guess_type(url=path.name)[0] or "application/octet-stream"),
            ("Content-Length", str(path.stat().st_size)),
        ):
            connection.putheader(key, value)

        connection.endheaders()
        sent = 0

        with open(path, "rb") as reader:
            for block in iter(lambda: reader.read(UPLOAD_BLOCK), b""):
                command.stop_point()
                connection.send(data=block)
                sent += len(block)
                moved(sent)

        response = connection.getresponse()
        status, body = response.status, response.read()
    except (OSError, http.client.HTTPException) as error:
        raise command.NetworkError(str(error) or type(error).__name__) from error
    finally:
        connection.close()

    if status != 201:
        try:
            message = json.loads(s=body).get("message", "")
        except (ValueError, AttributeError):
            message = ""

        raise command.GhError(f"HTTP {status}: {message or 'GitHub refused the upload'}")


# A failed try can leave an empty asset of this name behind, which would refuse the next one.
def upload_file(
    repo: str,
    tag: str,
    path: Path,
    report: Report = quiet,
    name: str = "",
    moved: Progress = quiet,
) -> None:
    def send() -> None:
        moved(0)
        old = releases.remote_assets(repo=repo, tag=tag).get(path.name)

        if old:
            releases.delete_asset(repo=repo, asset=old)

        release = json.loads(s=command.gh("api", f"repos/{repo}/releases/tags/{tag}"))["id"]
        post_asset(repo=repo, release=release, path=path, token=command.gh("auth", "token").strip(), moved=moved)

    progress.transfer(action=send, report=report, name=name or path.name)
