import argparse
import sys
import threading
import time

from .config import CHECK_INTERVAL, CHECK_RETRY, REPACK_WORKERS, WORKERS, base_dir
from .system import remove_old_program
from .vault import Vault


def periodic_check(vault: Vault) -> None:
    while True:
        vault.check()
        vault.check_app_update()
        vault.refresh_titles()
        vault.load_ports()
        time.sleep(CHECK_RETRY if vault.check_error else CHECK_INTERVAL)


def run_check(vault: Vault) -> int:
    vault.check()
    vault.check_app_update()

    if vault.app_update:
        print(f"A new NX Desk version is available: {vault.app_update.tag} ({vault.app_update.url})")

    if not vault.catalog:
        print("No catalog yet. Open the app to add one.")

        return 0

    if vault.check_error:
        print(f"Catalog check error: {vault.check_error}", file=sys.stderr)

        return 1

    updates = [entry for entry in vault.items if vault.status_of(entry=entry) == "update"]
    missing = sum(vault.status_of(entry=entry) == "missing" for entry in vault.items)

    for entry in updates:
        record = vault.state.get(entry.id)
        old = (record.version if record else "") or "?"

        print(f"Update available: {entry.name} ({old} -> {entry.version or '?'})")

    print(f"{vault.catalog.name}: {len(updates)} updates, {missing} not downloaded, {len(vault.items)} games total.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download, track and repackage game mods.")
    parser.add_argument(
        "--dir",
        default=str(base_dir()),
        help="root data folder; downloads go in downloaded/",
    )
    parser.add_argument("--check", action="store_true", help="only check for updates and exit")
    args = parser.parse_args()

    vault = Vault(base=args.dir)

    if args.check:
        return run_check(vault=vault)

    remove_old_program()

    try:
        from .ui.app import App  # Here, so that --check works without Qt.
    except ImportError as error:
        if not (error.name or "").startswith(("PySide6", "shiboken6")):
            raise

        print("PySide6 is not installed. Run: uv sync", file=sys.stderr)

        return 1

    threading.Thread(target=periodic_check, args=(vault,), daemon=True).start()

    for _ in range(WORKERS):
        threading.Thread(target=vault.worker, daemon=True).start()

    for _ in range(REPACK_WORKERS):
        threading.Thread(target=vault.repack_worker, daemon=True).start()

    app = App(vault=vault)

    if not vault.catalogs:
        app.later(action=app.open_manager)

    app.run()

    return 0
