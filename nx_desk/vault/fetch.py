import http.client
import threading
import time
import urllib.error
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from .. import net
from ..config import CHUNK, RETRIES
from ..schemas.catalog import Mod
from ..schemas.download import Fetched, FetchProgress, Pace
from ..schemas.state import DownloadRecord
from ..utils.files import sha256_of
from ..utils.http_headers import content_range_total, retry_after
from ..utils.sizes import format_size
from ..zips import Cancelled
from .catalogs import Catalogs
from .status import Statuses

# A job gives up after this many waits, so a permanent limit still ends in an error.
MAX_PAUSES = 2
PAUSE_FALLBACK = 60
# A limit that is still there after the server's own wait is treated as the hourly one.
LONG_PAUSE = 60 * 60


class Fetching(Catalogs, Statuses):
    def _fetch(self, entry: Mod, url: str, part: Path, cancel: threading.Event) -> None:
        size = entry.size  # 0 means the catalog did not say, so size checks are skipped
        have = part.stat().st_size if part.exists() else 0

        if size and have > size:
            part.unlink()
            have = 0

        if size and have == size:
            self._log_game(entry=entry, text="already fully downloaded earlier")

            return

        host = urlsplit(url=url).hostname or url
        resumed = f", resuming at {format_size(value=have)}" if have else ""
        self._log_game(entry=entry, text=f"downloading from {host}{resumed}")
        pace: Pace = Pace(time=time.monotonic(), done=have, started=time.monotonic(), start=have, mark=0)
        pieces = 0

        # Some servers cap each reply, so a short partial reply means asking for the next piece.
        while True:
            progress = self._fetch_piece(
                entry=entry,
                url=url,
                part=part,
                cancel=cancel,
                have=have,
                pace=pace,
            )
            done = progress.done
            total = progress.total
            partial = progress.partial
            pieces += 1
            expected = size or total

            if not expected or done >= expected:
                spent = max(0.001, time.monotonic() - pace.started)
                speed = format_size(value=(done - pace.start) / spent)
                split = f" in {pieces} pieces" if pieces > 1 else ""
                self._log_game(
                    entry=entry,
                    text=f"downloaded {format_size(value=done)}{split}, {spent:.0f}s at {speed}/s",
                )

                return

            if not partial or done <= have:
                raise OSError("connection dropped midway")

            if pieces == 1:
                self._log_game(
                    entry=entry,
                    text=f"the server sends {format_size(value=done - have)} per reply, asking for the rest",
                )

            have = done

    def _note_progress(self, entry: Mod, cancel: threading.Event, done: int, pace: Pace) -> None:
        now = time.monotonic()

        if now - pace.time < 0.5:
            return

        speed = (done - pace.done) / (now - pace.time)
        self._update_job(entry_id=entry.id, cancel=cancel, phase="downloading", done=done, speed=speed)
        pace.time = now
        pace.done = done
        size = entry.size
        mark = 10 * done // size if size else 0

        if size and mark > pace.mark and mark < 10:
            pace.mark = mark
            text = (
                f"{10 * mark}% · {format_size(value=done)} of {format_size(value=size)} · {format_size(value=speed)}/s"
            )
            self._log_game(entry=entry, text=text)

    def _fetch_piece(
        self,
        entry: Mod,
        url: str,
        part: Path,
        cancel: threading.Event,
        have: int,
        pace: Pace,
    ) -> FetchProgress:
        size = entry.size
        headers = {"Range": f"bytes={have}-"} if have else {}

        try:
            response = net.http_get(url=url, headers=headers)

        except urllib.error.HTTPError as error:
            if error.code == 416:
                part.unlink(missing_ok=True)

            raise

        with self.lock:
            if cancel.is_set():
                net.abort(response=response)
                raise Cancelled

            self.responses[entry.id] = response

        try:
            with response:
                partial = response.status == 206
                total = content_range_total(value=response.headers.get("Content-Range"))
                mode = "ab" if have and partial else "wb"
                done = have if mode == "ab" else 0

                with open(file=part, mode=mode) as handle:
                    while True:
                        if cancel.is_set():
                            raise Cancelled

                        block = response.read(CHUNK)

                        if cancel.is_set():
                            raise Cancelled

                        if not block:
                            break

                        done += len(block)

                        if size and done > size:
                            raise ValueError("file is larger than the size in the catalog")

                        handle.write(block)
                        self._note_progress(entry=entry, cancel=cancel, done=done, pace=pace)

                    self._update_job(entry_id=entry.id, cancel=cancel, done=done)

        finally:
            with self.lock:
                if self.responses.get(entry.id) is response:
                    del self.responses[entry.id]

        return FetchProgress(done=done, total=total, partial=partial)

    def _download(self, entry: Mod, cancel: threading.Event) -> Fetched:
        self.parts.mkdir(exist_ok=True)
        part = self.parts / f"{entry.id}.{(entry.sha256 or 'nohash')[:12]}.part"
        last_error = "download failed"

        for url in entry.urls:
            attempt = 0
            pauses = 0

            while attempt < RETRIES:
                attempt += 1

                try:
                    self._wait_for_pause(entry=entry, cancel=cancel)

                    with self.lock:
                        self.rate_strikes = 0

                    self._fetch(entry=entry, url=url, part=part, cancel=cancel)

                except Cancelled:
                    raise

                except urllib.error.HTTPError as error:
                    code, after = error.code, error.headers.get("Retry-After")
                    error.close()

                    if cancel.is_set():
                        raise Cancelled from error

                    last_error = f"HTTP {code}"
                    self._log_game(
                        entry=entry,
                        text=f"download error (try {attempt}): {last_error}",
                        level="warn",
                    )

                    if code == 429:
                        wait = retry_after(value=after) or PAUSE_FALLBACK

                        if pauses < MAX_PAUSES:
                            pauses += 1
                            attempt -= 1  # the wait is not a failed try
                            self._pause_downloads(entry=entry, wait=wait, cancel=cancel)

                            continue

                        last_error = "the server still limits downloads, try again later"
                        self._log_game(entry=entry, text=f"the server asks to wait {wait} seconds", level="warn")
                        break

                    if code in (404, 410):
                        break

                except (OSError, ValueError, http.client.HTTPException) as error:
                    if cancel.is_set():
                        raise Cancelled from error

                    last_error = str(error) or type(error).__name__
                    self._log_game(
                        entry=entry,
                        text=f"download error (try {attempt}): {last_error}",
                        level="warn",
                    )

                else:
                    try:
                        return self._finish(entry=entry, part=part, cancel=cancel)

                    except ValueError as error:
                        last_error = str(error) or type(error).__name__
                        self._log_game(entry=entry, text=last_error, level="error")
                        break

                if cancel.wait(timeout=attempt):
                    raise Cancelled

            if url != entry.urls[-1]:
                self._log_game(entry=entry, text="switching to another source", level="warn")
                part.unlink(missing_ok=True)

        raise RuntimeError(last_error)

    # A rate limit belongs to the machine, so every worker pauses; a job keeps its place and
    # continues after the wait the server gave.
    def _pause_downloads(self, entry: Mod, wait: float, cancel: threading.Event) -> None:
        with self.lock:
            self.rate_strikes += 1
            strikes = self.rate_strikes
            pause = max(1.0, wait) if strikes == 1 else max(float(LONG_PAUSE), wait)
            self.rate_until = max(self.rate_until, time.monotonic() + pause)

        self._update_job(entry_id=entry.id, cancel=cancel, phase="waiting_limit", speed=0)

        if strikes > 1:
            self._log_game(
                entry=entry,
                text="the server still limits downloads, so the pause is one hour",
                level="warn",
            )

        self._log_game(entry=entry, text=f"the server asks to wait {pause:.0f}s, pausing downloads", level="warn")

    def _wait_for_pause(self, entry: Mod, cancel: threading.Event) -> None:
        with self.lock:
            remaining = self.rate_until - time.monotonic()

        if remaining <= 0:
            return

        self._update_job(entry_id=entry.id, cancel=cancel, phase="waiting_limit", speed=0)
        self._log_game(entry=entry, text=f"waiting {remaining:.0f}s for the server's limit")

        if cancel.wait(timeout=remaining):
            raise Cancelled

        self._update_job(entry_id=entry.id, cancel=cancel, phase="downloading", speed=0)

    def _finish(self, entry: Mod, part: Path, cancel: threading.Event) -> Fetched:
        if not entry.sha256:
            self._log_game(entry=entry, text="catalog has no SHA-256, skipping verification", level="warn")

        else:
            self._update_job(entry_id=entry.id, cancel=cancel, phase="verifying", speed=0)
            self._log_game(entry=entry, text="verifying SHA-256")

            if sha256_of(path=part) != entry.sha256:
                self._log_game(entry=entry, text="SHA-256 does not match", level="error")
                part.unlink(missing_ok=True)

                raise ValueError("SHA-256 does not match")

            self._log_game(entry=entry, text="SHA-256 matches the catalog")

        return Fetched(wire=part)

    def _commit(self, entry: Mod, target: Path) -> Optional[Path]:
        with self.lock:
            previous = self._record_of(entry=entry)
            old_path = self.local_path(record=previous) if previous else None
            record: DownloadRecord = DownloadRecord(
                file=target.relative_to(self.root).as_posix(),
                sha256=entry.sha256,
                version=entry.version,
                game_version=entry.game_version,
                downloaded_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
            )

            # Every entry of the same file owns this copy.
            for entry_id in self._ids_of(entry=entry):
                self.state[entry_id] = record.model_copy()

            self._write_json(path=self.state_path, value=self.state)

            # Only this game's own copy is replaced: a different mod name is a separate
            # folder that the user may still want.
            if old_path and old_path != target and old_path.parent in self.game_folders(entry=entry):
                self._remove_replaced(path=old_path)

                return old_path

        return None

    def _remove_replaced(self, path: Path) -> None:
        # The new file is safe by now, so a failure here is not a failed download.
        try:
            path.unlink(missing_ok=True)

            if path.parent != self.root and not any(path.parent.iterdir()):
                path.parent.rmdir()

        except OSError:
            pass
