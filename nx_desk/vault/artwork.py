import contextlib
import http.client
import os
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from .. import credentials, net, steamgriddb
from ..config import ART_KEY_NAME, ART_LOOKUP_MAX_AGE, ART_LOOKUP_RULES, MAX_IMAGE, NO_CATALOG
from ..names import art_file_name, art_stem, art_stem_of, art_url, search_names
from ..schemas.artwork import ArtLookup, ArtSubject, SecretPlace
from ..schemas.catalog import ArtKind, Mod
from .base import VaultBase


class Artwork(VaultBase):
    def has_art_key(self) -> bool:
        return self.art_key.place != ""

    # True while a SteamGridDB lookup or one of its images is being fetched.
    def art_busy(self) -> bool:
        with self.lock:
            return self.art_active > 0

    @contextlib.contextmanager
    def _fetching_art(self, counted: bool = True) -> Iterator[None]:
        if not counted:
            yield

            return

        with self.lock:
            self.art_active += 1

        try:
            yield
        finally:
            with self.lock:
                self.art_active -= 1

    # An empty key forgets it. Returns where the key went, so Settings can say so.
    def set_art_key(self, key: str) -> SecretPlace:
        stored = credentials.save_secret(name=ART_KEY_NAME, value=key.strip(), folder=self.catalogs_dir)

        with self.lock:
            self.art_key = stored
            self.art_secret = key.strip()
            self.art_error = ""
            self.art_paused_until = 0.0
            # Games looked up without a working key may have art now.
            self.art_lookups = {name: found for name, found in self.art_lookups.items() if found.game_id}
            self.art_version += 1
            self._save_registry()

        return stored.place

    # Read once: a keyring may ask the system, which is slow.
    def _art_secret(self) -> str:
        with self.lock:
            secret, stored = self.art_secret, self.art_key

        if secret is None:
            secret = credentials.load_secret(name=ART_KEY_NAME, stored=stored, folder=self.catalogs_dir)

            with self.lock:
                if self.art_key == stored:
                    self.art_secret = secret

        return secret

    # SteamGridDB first when a key is set; the catalog's art for whatever it lacks.
    def art_sources(self, item: Mod) -> tuple[str, str]:
        found = self._art_lookup(item=item)
        cover, background = art_url(item=item, kind="cover"), art_url(item=item, kind="background")

        if found is None:
            return cover, background

        return found.cover or cover, found.background or background

    # Only SteamGridDB, for games that have no art of their own. None when it could not be asked: no
    # key, a refused key, a pause or a network error.
    def steamgrid_art(self, item: ArtSubject) -> tuple[str, str] | None:
        found = self._art_lookup(item=item)

        return (found.cover, found.background) if found else None

    def _art_lookup(self, item: ArtSubject) -> ArtLookup | None:
        if not self.has_art_key():
            return None

        name, *others = search_names(name=item.name)

        with self.lock:
            saved = self.art_lookups.get(name)
            stopped = bool(self.art_error) or time.monotonic() < self.art_paused_until

        if saved is not None and self._lookup_current(saved=saved):
            return saved

        secret = self._art_secret()

        if stopped or not secret:
            return saved

        try:
            with self._fetching_art():
                found = steamgriddb.lookup(name=name, key=secret, others=others)
        except steamgriddb.KeyRefused as error:
            with self.lock:
                self.art_error = str(error)

            return saved
        except steamgriddb.RateLimited as error:
            with self.lock:
                self.art_paused_until = time.monotonic() + error.wait

            return saved
        except steamgriddb.ArtworkError:
            return saved

        with self.lock:
            self.art_lookups[name] = found
            self._write_json(path=self.art_lookups_path, value=self.art_lookups)

        return found

    # A lookup made under older matching rules that found no cover is asked again, since better rules may find one.
    @staticmethod
    def _lookup_current(saved: ArtLookup) -> bool:
        if time.time() - saved.checked_at >= ART_LOOKUP_MAX_AGE:
            return False

        return saved.rules >= ART_LOOKUP_RULES or bool(saved.game_id and saved.cover)

    # Runs on an art thread. The file name holds a digest of the URL, so a new URL, such as SteamGridDB's once a
    # key is set, is a new name: the file is there already, or the old one is replaced.
    def fetch_art(self, item: ArtSubject, kind: ArtKind, url: str, art_dir: Path) -> Path | None:
        if not url:
            return None

        name = art_file_name(item=item, kind=kind, url=url)
        path = art_dir / name

        if path.is_file():
            return path

        try:
            with (
                self._fetching_art(counted=steamgriddb.is_steamgriddb(url=url)),
                net.http_get(url=url) as response,
            ):
                data = response.read(MAX_IMAGE + 1)
        except (OSError, ValueError, http.client.HTTPException):
            return None

        if len(data) > MAX_IMAGE:
            return None

        with self.art_lock:
            stem = art_stem(item=item, kind=kind)

            # The same art from another URL is the older file.
            for old in art_dir.glob(pattern=f"{stem}.*"):
                if old.name != name:
                    old.unlink(missing_ok=True)

            art_dir.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(suffix=".tmp")
            temp.write_bytes(data)
            os.replace(src=temp, dst=path)

        return path

    # Files of games no longer in the catalog go.
    def prune_art(self, items: Sequence[ArtSubject], art_dir: Path) -> None:
        # With no catalog there is no art to keep or fetch, and nothing should be made for it.
        if art_dir.name == NO_CATALOG:
            return

        stems = {art_stem(item=item, kind=kind) for item in items for kind in ("cover", "background")}

        with self.art_lock:
            art_dir.mkdir(parents=True, exist_ok=True)

            for old in art_dir.iterdir():
                if art_stem_of(file_name=old.name) not in stems:
                    old.unlink(missing_ok=True)

    def art_status(self) -> tuple[SecretPlace, str]:
        with self.lock:
            return self.art_key.place, self.art_error
