import time
from datetime import date, datetime

from ..config import LOG_MAX_AGE
from ..names import clean_game_name, game_of
from ..schemas.catalog import Mod
from ..schemas.common import LogEntry
from ..schemas.notice import Notice
from .base import VaultBase


# A log entry is (level, time, game, text); game is empty for lines that belong to no game.
def log_line(text: str, level: str, game: str = "") -> LogEntry:
    return level, f"{datetime.now():%H:%M:%S}", game, text


class Logs(VaultBase):
    # A session's lines also go to one file per day, so they outlive the app. Logging never stops
    # a job, so a file that cannot be written only loses the line there.
    def _keep_log(self, log: list[LogEntry], channel: str, text: str, level: str, game: str) -> None:
        line = log_line(text=text, level=level, game=game)

        with self.lock:
            log.append(line)
            flat = (f"{game}: {text}" if game else text).replace("\n", " ")

            try:
                self.logs_dir.mkdir(exist_ok=True)

                with open(self.logs_dir / f"nx-desk-{date.today()}.log", "a", encoding="utf-8") as handle:
                    handle.write(f"{line[1]} {level.upper():5} {channel:8} {flat}\n")
            except OSError:
                pass

    def _notice(self, title: str, text: str) -> None:
        with self.lock:
            if self.notify:
                self.notices.append(Notice(title=title, text=text))

    def take_notices(self) -> list[Notice]:
        with self.lock:
            notices, self.notices = self.notices, []

            return notices

    def _prune_logs(self) -> None:
        oldest = time.time() - LOG_MAX_AGE

        try:
            for path in self.logs_dir.glob("nx-desk-*.log"):
                if path.stat().st_mtime < oldest:
                    path.unlink()
        except OSError:
            pass

    def _log_github(self, text: str, level: str = "info", game: str = "") -> None:
        self._keep_log(log=self.github_log, channel="github", text=text, level=level, game=game)

    # GitHub lines group by game; the mod and version start each line, as one game may have several.
    def _log_folder(self, folder_name: str, text: str, level: str = "info") -> None:
        game = game_of(folder=folder_name)
        label = folder_name[len(game) + 3 :] if game else ""
        self._log_github(text=f"{label}  {text}" if label else text, level=level, game=game or folder_name)

    def _log_download(self, text: str, level: str = "info", game: str = "") -> None:
        self._keep_log(log=self.download_log, channel="download", text=text, level=level, game=game)

    def _log_game(self, entry: Mod, text: str, level: str = "info") -> None:
        self._log_download(text=text, level=level, game=clean_game_name(name=entry.name))
