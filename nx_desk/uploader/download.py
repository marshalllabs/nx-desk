from pathlib import Path
from urllib.parse import urljoin

from ..schemas.common import Progress
from ..utils.callbacks import quiet
from . import api, archive, command


def asset(repo: str, asset_id: int, target: Path, moved: Progress = quiet) -> None:
    url = api.endpoint(path=f"repos/{repo}/releases/assets/{asset_id}")

    for _ in range(6):
        with api.response(url=url, accept="application/octet-stream") as reply:
            if reply.status in (301, 302, 303, 307, 308):
                location = reply.getheader("Location")

                if not location:
                    raise command.GitHubError("GitHub asset redirect is missing its destination")

                url = urljoin(base=url, url=location)
                continue

            api.check(reply=reply)
            expected = reply.getheader("Content-Length")
            done = 0
            moved(done)

            with target.open(mode="wb") as writer:
                while True:
                    command.stop_point()
                    block = reply.read(archive.BLOCK)

                    if not block:
                        break

                    writer.write(block)
                    done += len(block)
                    moved(done)

            if expected and done != int(expected):
                raise command.NetworkError("GitHub download ended before the full asset arrived")

            return

    raise command.GitHubError("GitHub asset redirected too many times")
