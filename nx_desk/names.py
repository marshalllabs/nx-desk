import hashlib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlsplit

from .config import (
    DISPLAY_VERSION,
    IMAGE_SUFFIXES,
    MISSING_VERSION,
    ROMAN_NUMERAL,
    TITLE_ID,
)
from .schemas.artwork import ArtSubject
from .schemas.catalog import ArtKind, Mod

# A saved mod folder: <Game> - [<mod>] - [<version>].
GAME_FOLDER = re.compile(pattern=r"(.+) - \[[^\[\]]+\] - \[[^\[\]]+\]$")
GAME_FOLDER_VERSION = re.compile(pattern=r" - \[[^\[\]]+\] - \[([^\[\]]+)\]$")
BUILD_SUFFIX = re.compile(pattern=r"-v\d+\]$")


def game_of(folder: str) -> str:
    match = GAME_FOLDER.match(string=folder)

    return match.group(1) if match else ""


# Games that appear more than once, by key, for showing them under one row. games maps each key
# to its game name, or "" when there is none.
def shared_games(games: Dict[str, str]) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}

    for key, game in games.items():
        if game:
            found.setdefault(game, []).append(key)

    return {game: keys for game, keys in found.items() if len(keys) > 1}


# The zip inside may leave out the build number, as in [1.0.2] for a folder ending [1.0.2-v131072].
def folder_zip_names(folder: str) -> List[str]:
    names = [f"{folder}.zip"]

    if BUILD_SUFFIX.search(string=folder):
        names.append(f"{BUILD_SUFFIX.sub(repl=']', string=folder)}.zip")

    return names


def safe_name(name: str) -> str:
    cleaned = re.sub(pattern=r'[:/\\?*"<>|\x00-\x1f]+', repl=" ", string=name)

    return re.sub(pattern=r"\s+", repl=" ", string=cleaned).strip(" .")[:120]


def art_slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    text = text.encode(encoding="ascii", errors="ignore").decode(encoding="ascii").replace("'", "")

    return re.sub(pattern=r"[^a-z0-9]+", repl="-", string=text.lower()).strip("-")


# Words a port adds to its name to say where it runs, not part of the game's name.
PORT_WORDS = {"nx", "switch", "port", "for"}


# The names to search a game under: its cleaned name first, then the name without those trailing words and
# with the separators of a repository name turned into spaces ("ff4_nx" gives "ff4").
def search_names(name: str) -> List[str]:
    names = [clean_game_name(name=name)]
    words = [word for word in re.split(pattern=r"[\s_\-]+", string=strip_accents(text=name).strip()) if word]

    while words and words[-1].casefold() in PORT_WORDS:
        words.pop()

    other = clean_game_name(name=re.sub(pattern=r"[._\-]+", repl=" ", string=" ".join(words)))

    if len(other) >= 3 and other != names[0]:
        names.append(other)

    return names


def art_url(item: Mod, kind: ArtKind) -> str:
    return item.cover if kind == "cover" else item.background


def art_stem(item: ArtSubject, kind: ArtKind) -> str:
    return f"{art_slug(name=item.name) or item.id}-{kind}"


# A short digest of the URL goes into the name, so another URL, such as SteamGridDB's once a key is set, makes
# another file name and no list of which file came from which URL is needed.
def art_name(stem: str, url: str) -> str:
    suffix = Path(urlsplit(url=url).path).suffix.lower()

    if suffix not in IMAGE_SUFFIXES:
        suffix = ".img"

    return f"{stem}.{hashlib.sha256(string=url.encode(encoding='utf-8')).hexdigest()[:8]}{suffix}"


def art_file_name(item: ArtSubject, kind: ArtKind, url: str) -> str:
    return art_name(stem=art_stem(item=item, kind=kind), url=url)


# The stem a file name was made from: art_slug has no dots, so everything before the first one.
def art_stem_of(file_name: str) -> str:
    return file_name.split(sep=".", maxsplit=1)[0]


def display_version(game_version: str) -> str:
    match = DISPLAY_VERSION.search(string=game_version)

    return match.group(0) if match else MISSING_VERSION


def title_name(names: Dict[str, str], title: str) -> str:
    # Update title IDs end in 800 and otherwise match the base game.
    name = names.get(title) or names.get(title[:-3] + "000") or ""

    return re.sub(pattern=r"[™®©]", repl="", string=name)


def tidy_capitals(name: str) -> str:

    def tidy(word: re.Match[str]) -> str:
        text = word.group(0)

        if TITLE_ID.match(string=text):
            return text

        return re.sub(
            pattern=r"[^\W\d_]+",
            repl=lambda part: (
                part.group(0) if ROMAN_NUMERAL.fullmatch(string=part.group(0)) else part.group(0).capitalize()
            ),
            string=text,
        )

    return re.sub(pattern=r"[^\s-]+", repl=tidy, string=name) if name.isupper() else name


def strip_accents(text: str) -> str:
    # Marks on other scripts stay, since they change the letter there.
    kept: List[str] = []

    for char in unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D")):
        if not (unicodedata.category(char) == "Mn" and kept and ord(kept[-1]) < 0x250):
            kept.append(char)

    return unicodedata.normalize("NFC", "".join(kept))


def clean_game_name(name: str) -> str:
    text = re.sub(pattern=r"[/\\|]+", repl=" ", string=strip_accents(text=name))
    text = "".join(char for char in text if char in " -" or char.isspace() or unicodedata.category(char)[0] in "LNM")
    text = re.sub(pattern=r"\s+", repl=" ", string=text).strip(" -")[:120]

    return tidy_capitals(name=text) or safe_name(name=name)


def game_folder(name: str, mod: str) -> str:
    return f"{clean_game_name(name=name)} - [{mod}]"


def version_label(version: str) -> str:
    shown = display_version(game_version=version)

    return "Miss" if shown == MISSING_VERSION else shown


# The game version a saved folder was named with, such as "1.0.2" in "Game - [VI] - [1.0.2]".
def folder_version(folder: str) -> str:
    match = GAME_FOLDER_VERSION.search(string=folder or "")

    return match.group(1) if match else ""


def download_path(name: str, version: str, mod: str) -> Path:
    folder = f"{game_folder(name=name, mod=mod)} - [{version_label(version=version)}]"

    return Path(folder) / f"{folder}.zip"
