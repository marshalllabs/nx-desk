from typing import Dict, List

from ..schemas.switch_sd import (
    MountedVolume,
    SDCategory,
    SDContentIdentity,
    SDSnapshot,
)
from ..switch_sd import detect, scan
from ..zips import Cancelled
from .base import VaultBase


class SwitchSD(VaultBase):
    def switch_snapshot(self) -> SDSnapshot:
        with self.lock:
            return self.sd_job.model_copy(deep=True)

    def _switch_names(self) -> Dict[str, SDContentIdentity]:
        categories: Dict[str, SDCategory] = {"games": "Game", "system": "System content", "sysmodules": "Sysmodule"}

        with self.lock:
            names = {
                title_id.upper(): SDContentIdentity(name=name, category="Game")
                for title_id, name in self.titles.items()
            }

            for row in self.title_rows:
                names[row.id.upper()] = SDContentIdentity(
                    name=row.name,
                    category=categories.get(row.section, ""),
                )

            for item in self.items:
                if item.title_id:
                    names.setdefault(item.title_id.upper(), SDContentIdentity(name=item.name, category="Game"))

        return names

    def select_switch_card(self, root: str) -> None:
        with self.lock:
            if self.sd_job.phase != "idle":
                return

            self.sd_job.selected = root
            self.sd_job.titles = []
            self.sd_job.revision += 1

    def refresh_switch_cards(self, volumes: List[MountedVolume], force: bool = False) -> None:
        if not self.sd_lock.acquire(blocking=False):
            return

        try:
            cards = detect.discover(volumes=volumes)
            names = self._switch_names()

            with self.lock:
                selected = self.sd_job.selected
                previous = next((card for card in self.sd_job.cards if str(card.root) == selected), None)
                current = next((card for card in cards if str(card.root) == selected), None)
                if current is None and cards:
                    current = cards[0]

                self.sd_job.cards = cards
                self.sd_job.revision += 1

                if current is None:
                    self.sd_job.selected = ""
                    self.sd_job.titles = []
                    self.sd_job.message = "No SD card detected."

                    return

                self.sd_job.selected = str(current.root)

                if not force and current == previous:
                    self.sd_job.titles = scan.relabel(rows=self.sd_job.titles, names=names)

                    return

                self.sd_cancel.clear()
                self.sd_job.phase = "scanning"
                self.sd_job.message = "Scanning card contents and verifying NX Desk metadata…"
                self.sd_job.failed = False

            titles = scan.scan(card=current, names=names, cancel=self.sd_cancel)
            recovery = list((current.root / "atmosphere").glob(pattern=".nx-desk-copy-*"))

            with self.lock:
                self.sd_job.titles = titles
                self.sd_job.message = (
                    f"{len(titles)} content folders. Game installation and game versions are not scanned."
                )

                if recovery:
                    self.sd_job.message += " Interrupted-copy data exists; keep it until recovery is complete."

                self.sd_job.revision += 1

        except (OSError, ValueError, Cancelled) as error:
            with self.lock:
                self.sd_job.failed = True
                self.sd_job.message = "Scan cancelled." if isinstance(error, Cancelled) else str(error)
                self.sd_job.titles = []

        finally:
            with self.lock:
                self.sd_job.phase = "idle"

            self.sd_lock.release()

    def cancel_switch_job(self) -> None:
        self.sd_cancel.set()
