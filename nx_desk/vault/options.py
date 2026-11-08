import shutil
from pathlib import Path

from ..config import clean_compression
from ..names import safe_name, set_size_units
from .jobs import Jobs


class Options(Jobs):
    def move_download_dir(self, new_dir: str) -> str:
        new = Path(new_dir).expanduser().resolve()

        with self.lock:
            if self.busy():
                raise ValueError("Wait for downloads to finish before moving.")

            old = self._download_root()

        if old == new:
            return str(new)

        new.mkdir(parents=True, exist_ok=True)

        for item in sorted(old.iterdir()) if old.is_dir() else []:
            target = new / item.name

            if target.exists():
                raise ValueError(f"{item.name} already exists in the new folder")

            shutil.move(src=str(item), dst=str(target))

        with self.lock:
            self.download_dir = str(new)
            self.root = new / self.root.name
            self._save_registry()

        return str(new)

    def set_download_dir(self, text: str) -> None:
        # Workers read self.root, so it stays put while anything is downloading.
        text = text.strip()

        with self.lock:
            if text == self.download_dir or self.busy():
                return

            self.download_dir = text
            self.root = self._download_root() / self.root.name
            self._save_registry()

    def set_upload_settings(self, source: str, repo: str, tag: str) -> None:
        with self.lock:
            self.upload_source, self.upload_repo, self.upload_tag = source.strip(), repo.strip(), tag.strip()
            self._save_registry()

    def set_auto_upload(self, enabled: bool) -> None:
        with self.lock:
            if bool(enabled) != self.auto_upload:
                self.auto_upload = bool(enabled)
                # Deleting only makes sense after an upload, so it goes off with it.
                self.auto_delete = self.auto_delete and self.auto_upload
                self._save_registry()

    def set_auto_delete(self, enabled: bool) -> None:
        with self.lock:
            enabled = bool(enabled) and self.auto_upload

            if enabled != self.auto_delete:
                self.auto_delete = enabled
                self._save_registry()

    def set_upload_delete(self, enabled: bool) -> None:
        with self.lock:
            if bool(enabled) != self.upload_delete:
                self.upload_delete = bool(enabled)
                self._save_registry()

    def set_auto_repo(self, repo: str) -> None:
        with self.lock:
            if repo.strip() != self.auto_repo:
                self.auto_repo = repo.strip()
                self._save_registry()

    def set_font(self, family: str, size: int) -> None:
        with self.lock:
            self.font_family, self.font_size = family.strip(), max(0, size)
            self._save_registry()

    def set_notify(self, enabled: bool) -> None:
        with self.lock:
            self.notify = bool(enabled)
            self._save_registry()

    def set_ports_view(self, view: str) -> None:
        with self.lock:
            self.ports_view = "grid" if view == "grid" else "list"
            self._save_registry()

    def set_catalog_view(self, view: str) -> None:
        with self.lock:
            self.catalog_view = "grid" if view == "grid" else "list"
            self._save_registry()

    def set_homebrews_view(self, view: str) -> None:
        with self.lock:
            self.homebrews_view = "grid" if view == "grid" else "list"
            self._save_registry()

    def set_size_units(self, units: str) -> None:
        with self.lock:
            set_size_units(units=units)
            self.size_units = units
            self._save_registry()

    # Each repack reads this when it starts, so a change reaches the mods not repacked yet.
    def set_compression(self, level: int) -> None:
        with self.lock:
            self.compression = clean_compression(value=level)
            self._save_registry()

    def set_mod_name(self, name: str) -> None:
        # A reviewed scan shows paths built from the old name, so it has to be redone.
        name = safe_name(name=name)

        with self.lock:
            if name == self.mod_name:
                return

            self.mod_name = name
            self._save_registry()
