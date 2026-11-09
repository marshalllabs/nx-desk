import http.client
import shutil
import time
from typing import Dict, List, Optional
from urllib.parse import urlsplit

from ..catalog.parse import fetch_catalog
from ..catalog.values import clean_mapping
from ..config import CATALOG_FILE
from ..schemas.catalog import Catalog, CatalogChanges, CatalogEdit, CatalogSource, Mod
from ..utils.text import few_names, plural
from .catalog_moves import CatalogMoves


# Entries new to a fresh catalog, and ones whose file changed, against the list it replaces.
def catalog_news(old: List[Mod], new: List[Mod]) -> CatalogChanges:
    before = {item.id: item for item in old}
    added = [item.name for item in new if item.id not in before]
    changed = [
        item.name
        for item in new
        if item.id in before and (item.sha256, item.version) != (before[item.id].sha256, before[item.id].version)
    ]

    return CatalogChanges(added=added, changed=changed)


class Catalogs(CatalogMoves):
    def add_catalog(self, name: str, url: str, mapping: Optional[Dict[str, str]] = None) -> Catalog:
        url = url.strip()

        if not url.startswith("https://"):
            raise ValueError("URL must start with https://")

        mapping = clean_mapping(mapping=mapping)

        with self.lock:
            if any(catalog.url == url for catalog in self.catalogs):
                raise ValueError("this catalog is already in the list")

        fetched = fetch_catalog(url=url, mapping=mapping)
        raw = fetched.raw
        name = name.strip() or urlsplit(url=url).hostname or "catalog"

        with self.lock:
            if self.busy():
                raise ValueError("wait for downloads to finish before adding a catalog")

            folder = self._free_folder(name=name)
            catalog: Catalog = Catalog(
                name=name,
                url=url,
                folder=folder,
                mapping=mapping,
            )
            self.catalogs.append(catalog)
            self._write_bytes(path=self._catalog_file(folder=folder, name=CATALOG_FILE), data=raw)
            self._use_catalog(catalog=catalog)
            self.checked_at = time.time()
            self._save_registry()

        return catalog

    # A new name also gives the catalog a new folder, with its downloads, state and release (see CatalogMoves);
    # when that cannot be done, the folder stays, so they keep belonging to the catalog.
    def edit_catalog(
        self,
        folder: str,
        name: str,
        url: str,
        mapping: Optional[Dict[str, str]] = None,
    ) -> CatalogEdit:
        url = url.strip()

        if not url.startswith("https://"):
            raise ValueError("URL must start with https://")

        mapping = clean_mapping(mapping=mapping)

        with self.lock:
            catalog = next((c for c in self.catalogs if c.folder == folder), None)

            if catalog is None:
                raise ValueError("this catalog is no longer in the list")

            if any(other.url == url and other is not catalog for other in self.catalogs):
                raise ValueError("another catalog already uses this URL")

        fetched = fetch_catalog(url=url, mapping=mapping)
        raw = fetched.raw
        document = fetched.document
        new_name = name.strip() or catalog.name
        notes: List[str] = []

        with self.lock:
            if not any(c is catalog for c in self.catalogs):
                raise ValueError("this catalog is no longer in the list")

            if catalog is self.catalog and self.busy():
                raise ValueError("wait for downloads to finish before changing this catalog")

            wanted = self._free_folder(name=new_name, skip=catalog) if new_name != catalog.name else catalog.folder

        # Talks to GitHub, so it runs outside the lock; it changes nothing unless it can finish.
        if wanted != catalog.folder:
            notes = self._rename_folder(catalog=catalog, new=wanted)

        with self.lock:
            if not any(c is catalog for c in self.catalogs):
                raise ValueError("this catalog is no longer in the list")

            active = catalog is self.catalog

            if active and self.busy():
                raise ValueError("wait for downloads to finish before changing this catalog")

            catalog.name = new_name
            catalog.url = url
            catalog.mapping = mapping
            self._write_bytes(path=self._catalog_file(folder=catalog.folder, name=CATALOG_FILE), data=raw)

            if active:
                self.items = self._named(items=document.items)
                self.check_error = None
                self.checked_at = time.time()

            self._save_registry()

        return CatalogEdit(catalog=catalog, count=len(document.items), notes=notes)

    def select_catalog(self, folder: str) -> None:
        with self.lock:
            catalog = next(c for c in self.catalogs if c.folder == folder)

            if catalog is not self.catalog:
                self._use_catalog(catalog=catalog)
                self._save_registry()

    # Its cached catalog, download records and art go with it; the downloaded mods stay where they are.
    def remove_catalog(self, folder: str) -> None:
        with self.lock:
            self.catalogs = [catalog for catalog in self.catalogs if catalog.folder != folder]

            if self.catalog and self.catalog.folder == folder:
                self._use_catalog(catalog=self.catalogs[0] if self.catalogs else None)

            self._save_registry()

        for leftover in (self.catalogs_dir / folder, self.base / "covers" / folder):
            shutil.rmtree(path=leftover, ignore_errors=True)

    def _report_news(self, catalog: Catalog, old: List[Mod], new: List[Mod]) -> None:
        news = catalog_news(old=old, new=new)
        added = news.added
        changed = news.changed
        lines = []

        if added:
            lines.append(f"{plural(count=len(added), word='new mod')}: {few_names(names=added)}")

        if changed:
            lines.append(f"{plural(count=len(changed), word='update')}: {few_names(names=changed)}")

        if lines:
            self._notice(title=catalog.name, text="\n".join(lines))

    def check(self) -> None:
        with self.lock:
            if self.checking or not self.catalog:
                return

            self._clear_failed_jobs()
            self.checking = True
            catalog = self.catalog
            source = CatalogSource(url=catalog.url, mapping=catalog.mapping)

        try:
            fetched = fetch_catalog(url=source.url, mapping=clean_mapping(mapping=source.mapping))
            raw = fetched.raw
            document = fetched.document

            with self.lock:
                # The user may have switched or edited catalogs while this one was loading.
                if self.catalog is catalog and (catalog.url == source.url and catalog.mapping == source.mapping):
                    self._write_bytes(path=self.cache_path, data=raw)
                    old = self.items
                    self.items = self._named(items=document.items)

                    # A first load has nothing to compare with, so every game would count as new.
                    if old:
                        self._report_news(catalog=catalog, old=old, new=self.items)

                    self.check_error = None
                    self.checked_at = time.time()

            self.refresh_release_state()

        except (OSError, ValueError, http.client.HTTPException) as error:
            with self.lock:
                if self.catalog is catalog:
                    self.check_error = str(error) or type(error).__name__

        finally:
            with self.lock:
                self.checking = False
