import re
from collections import Counter

from ..schemas.port import Port
from .values import as_text, https_or_empty

TEXT_LIMIT = 200
# The marks of the status legend; a variation selector may follow them.
STATUS_NAMES = {
    "⬛": "Does not boot",
    "🟥": "Boots to title",
    "🟧": "Boots, unplayable",
    "🟨": "Playable",
    "🟩": "Completable",
    "✳": "Feature complete",
}
# A theme color for each mark: trouble, partly there, done.
STATUS_TONES = {"⬛": "bad", "🟥": "bad", "🟧": "accent", "🟨": "accent", "🟩": "ok", "✳": "ok"}
HOSTS = {"github": "GitHub", "gitlab": "GitLab"}
GITHUB_REPO = re.compile(pattern=r"^https://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)/?$")
# The card GitHub draws for any repository, its name and description on a plain background.
CARD_URL = "https://opengraph.githubassets.com/1/{owner}/{repo}"


def text_of(value: object) -> str:
    return as_text(value=value).strip()[:TEXT_LIMIT]


# The list from the gist: {"ports": [...]}. It is untrusted, so each field is cleaned by hand and a
# row without an id or a name is dropped.
def parse_ports(data: object) -> list[Port]:
    raw_rows = data.get("ports") if isinstance(data, dict) else None
    rows: list[Port] = []
    seen: set[str] = set()

    for raw in raw_rows if isinstance(raw_rows, list) else ():
        if not isinstance(raw, dict):
            continue

        port_id, name = text_of(value=raw.get("id")), text_of(value=raw.get("name"))

        if not port_id or not name or port_id in seen:
            continue

        seen.add(port_id)
        rows.append(
            Port(
                id=port_id,
                name=name,
                platform=text_of(value=raw.get("platform")) or "Other",
                kind="emulator" if text_of(value=raw.get("kind")).lower() == "emulator" else "port",
                emulates=text_of(value=raw.get("emulates")),
                version=text_of(value=raw.get("version")),
                updated=text_of(value=raw.get("updated")),
                url=https_or_empty(value=raw.get("url")),
                host=text_of(value=raw.get("host")).lower(),
                thread=https_or_empty(value=raw.get("thread")),
                status=text_of(value=raw.get("status")),
            ),
        )

    return rows


# Art of last resort for a GitHub repository that SteamGridDB has none for; empty for other hosts.
def card_url(port: Port) -> str:
    match = GITHUB_REPO.match(string=port.url)

    return CARD_URL.format(owner=match.group(1), repo=match.group(2)) if match else ""


def status_mark(status: str) -> str:
    return status.replace("️", "").strip()


def status_label(status: str) -> str:
    return STATUS_NAMES.get(status_mark(status=status), status.strip())


def status_tone(status: str) -> str:
    return STATUS_TONES.get(status_mark(status=status), "ink")


def host_label(host: str) -> str:
    return HOSTS.get(host, host.capitalize() if host else "")


# Every word of the query must appear somewhere in the row.
def find_ports(rows: list[Port], query: str) -> list[Port]:
    words = query.casefold().split()

    if not words:
        return rows

    def haystack(port: Port) -> str:
        parts = (port.name, port.id, port.platform, port.emulates, port.version, status_label(status=port.status))

        return " ".join(parts).casefold()

    return [port for port in rows if all(word in haystack(port=port) for word in words)]


# Platforms by name, each with how many entries it has.
def platform_counts(rows: list[Port]) -> list[tuple[str, int]]:
    counts = Counter(port.platform for port in rows)

    return sorted(counts.items(), key=lambda pair: pair[0].casefold())
