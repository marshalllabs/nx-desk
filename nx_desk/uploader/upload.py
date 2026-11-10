import http.client
import mimetypes
from pathlib import Path
from urllib.parse import quote, urlencode

from .. import net
from ..config import user_agent
from ..schemas.common import Progress, Report
from ..utils.callbacks import quiet
from ..utils.release_state import find_asset_name
from . import api, command, progress, releases

UPLOAD_HOST = "uploads.github.com"
UPLOAD_BLOCK = 256 * 1024
UPLOAD_TIMEOUT = 120


# Stream uploads in counted blocks without buffering the archive.
# The token stays in memory and goes only to GitHub's upload host.
def post_asset(repo: str, release: int, path: Path, token: str, moved: Progress) -> None:
    connection = http.client.HTTPSConnection(host=UPLOAD_HOST, timeout=UPLOAD_TIMEOUT, context=net.SSL_CONTEXT)
    query = urlencode(query={"name": path.name})

    try:
        with command.interruptible(connection=connection):
            connection.putrequest(method="POST", url=f"/repos/{quote(string=repo)}/releases/{release}/assets?{query}")

            for key, value in (
                ("Authorization", f"Bearer {token}"),
                ("Accept", "application/vnd.github+json"),
                ("X-GitHub-Api-Version", api.API_VERSION),
                ("User-Agent", user_agent()),
                ("Content-Type", mimetypes.guess_type(url=path.name)[0] or "application/octet-stream"),
                ("Content-Length", str(path.stat().st_size)),
            ):
                connection.putheader(key, value)

            connection.endheaders()
            sent = 0

            with open(file=path, mode="rb") as reader:
                for block in iter(lambda: reader.read(UPLOAD_BLOCK), b""):
                    command.stop_point()
                    connection.send(data=block)
                    sent += len(block)
                    moved(sent)

            response = connection.getresponse()
            api.check(reply=response)
            response.read(65536)

            if response.status != 201:
                raise command.GitHubError("GitHub did not confirm the uploaded asset")

    except (OSError, http.client.HTTPException) as error:
        command.stop_point()

        raise command.NetworkError("GitHub upload connection interrupted; try again.") from error

    finally:
        connection.close()


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
        assets = releases.remote_assets(repo=repo, tag=tag)
        old_name = find_asset_name(name=path.name, names=list(assets))
        old = assets.get(old_name) if old_name else None

        if old:
            releases.delete_asset(repo=repo, asset=old)

        release = releases.by_tag(repo=repo, tag=tag).id
        post_asset(repo=repo, release=release, path=path, token=command.token(), moved=moved)

    progress.transfer(action=send, report=report, name=name or path.name)
