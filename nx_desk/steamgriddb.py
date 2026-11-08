import http.client
import json
import time
import urllib.error
from collections.abc import Sequence
from urllib.parse import quote, urlencode, urlsplit

from . import net
from .config import ART_LOOKUP_RULES
from .schemas.artwork import ArtLookup
from .utils.http_headers import retry_after
from .utils.text import likeness

API = "https://www.steamgriddb.com/api/v2"
REPLY_LIMIT = 1024 * 1024
# A search hit counts only when its name is this alike to the one asked for; the first hit is not enough.
MIN_LIKENESS = 0.6
# Cover art tried first: the tall box art the banner draws beside the background.
GRID_FILTERS: tuple[dict[str, str], ...] = (
    {"dimensions": "600x900", "types": "static", "nsfw": "false", "humor": "false"},
    {"types": "static", "nsfw": "false", "humor": "false"},
    {},
)
HERO_FILTERS: tuple[dict[str, str], ...] = (
    {"types": "static", "nsfw": "false", "humor": "false"},
    {},
)


# Its images come from its own CDN, such as cdn2.steamgriddb.com.
def is_steamgriddb(url: str) -> bool:
    host = urlsplit(url=url).hostname or ""

    return host == "steamgriddb.com" or host.endswith(".steamgriddb.com")


class ArtworkError(Exception):
    pass


class KeyRefused(ArtworkError):
    pass


class RateLimited(ArtworkError):
    def __init__(self, wait: int) -> None:
        super().__init__(f"SteamGridDB asks to wait {wait} seconds")
        self.wait = wait


# Replies are untrusted: anything but {"success": true, "data": [...]} counts as no data.
def get_data(path: str, key: str, query: dict[str, str]) -> list[object] | None:
    url = f"{API}{path}" + (f"?{urlencode(query=query)}" if query else "")

    try:
        with net.http_get(url=url, headers={"Authorization": f"Bearer {key}"}) as response:
            raw = response.read(REPLY_LIMIT + 1)
    except urllib.error.HTTPError as error:
        code = error.code
        wait = retry_after(value=error.headers.get("Retry-After")) or 60
        error.close()

        if code in (401, 403):
            raise KeyRefused("SteamGridDB refused the API key") from None

        if code == 429:
            raise RateLimited(wait=wait) from None

        # 404 is an unknown game; 400 a filter the server does not take, so the next one is tried.
        if code in (400, 404):
            return None

        raise ArtworkError(f"SteamGridDB answered HTTP {code}") from None
    except (OSError, http.client.HTTPException) as error:
        raise ArtworkError(str(error) or type(error).__name__) from None

    if len(raw) > REPLY_LIMIT:
        return None

    try:
        reply = json.loads(s=raw)
    except ValueError:
        return None

    if not isinstance(reply, dict) or reply.get("success") is not True:
        return None

    data = reply.get("data")

    return data if isinstance(data, list) else None


# The hit whose name is most like the one asked for, the earlier one on a tie; 0 when none is alike enough.
def search_game(name: str, key: str) -> int:
    best, best_score = 0, 0.0

    for found in get_data(path=f"/search/autocomplete/{quote(name, safe='')}", key=key, query={}) or []:
        if not isinstance(found, dict):
            continue

        game_id = found.get("id")

        if not isinstance(game_id, int) or isinstance(game_id, bool) or game_id <= 0:
            continue

        title = found.get("name")
        score = likeness(left=name, right=title) if isinstance(title, str) else MIN_LIKENESS

        if score > best_score:
            best, best_score = game_id, score

    return best if best_score >= MIN_LIKENESS else 0


def first_image(kind: str, game_id: int, key: str, filters: tuple[dict[str, str], ...]) -> str:
    for query in filters:
        for image in get_data(path=f"/{kind}/game/{game_id}", key=key, query=query) or []:
            url = image.get("url") if isinstance(image, dict) else None

            if isinstance(url, str) and url.startswith("https://") and len(url) < 2048:
                return url

    return ""


# The name first, then its other spellings, until one has art. A game found without art is kept in case
# no other spelling does better.
def lookup(name: str, key: str, others: Sequence[str] = ()) -> ArtLookup:
    kept: ArtLookup | None = None

    for candidate in (name, *others):
        game_id = search_game(name=candidate, key=key)

        if not game_id:
            continue

        found = ArtLookup(
            game_id=game_id,
            cover=first_image(kind="grids", game_id=game_id, key=key, filters=GRID_FILTERS),
            background=first_image(kind="heroes", game_id=game_id, key=key, filters=HERO_FILTERS),
            checked_at=time.time(),
            rules=ART_LOOKUP_RULES,
        )

        if found.cover or found.background:
            return found

        kept = kept or found

    return kept or ArtLookup(checked_at=time.time(), rules=ART_LOOKUP_RULES)
