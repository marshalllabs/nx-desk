import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Dict, Union

from .config import PROGRAM_NAME
from .schemas.update import AppUpdate


def asset_name() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()

    return f"{PROGRAM_NAME}-{system}-{'x86_64' if machine == 'amd64' else machine}.zip"


def program_path() -> Path:
    executable = Path(sys.executable).resolve()

    return executable.parents[2] if sys.platform == "darwin" else executable


def can_self_update(update: AppUpdate) -> bool:
    return bool(
        getattr(sys, "frozen", False) and update.asset and os.access(path=program_path().parent, mode=os.W_OK),
    )


def backup_path(program: Path) -> Path:
    return program.with_name(name=program.name + ".old")


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path=path)

    elif path.exists():
        path.unlink()


def remove_old_program() -> None:
    # A program cannot delete itself while running, so the next start removes the backup.
    if getattr(sys, "frozen", False):
        try:
            remove_path(path=backup_path(program=program_path()))

        except OSError:
            pass


def extract_program(archive: Path, target: Path, name: str) -> Path:
    if sys.platform == "darwin":
        # ditto keeps the symlinks and signature inside the .app.
        subprocess.run(args=["ditto", "-x", "-k", str(archive), str(target)], check=True)

    else:
        with zipfile.ZipFile(file=archive) as source:
            for info in source.infolist():
                parts = info.filename.split(sep="/")

                if parts[0] == name and ".." not in parts:
                    source.extract(member=info, path=target)

    extracted = target / name

    if not extracted.exists():
        raise RuntimeError(f"the update has no {name}")

    if sys.platform != "win32" and extracted.is_file():
        extracted.chmod(0o755)

    return extracted


def swap_program(new: Path, program: Path) -> None:
    # Every OS allows moving a running program aside, but not overwriting it.
    backup = backup_path(program=program)
    remove_path(path=backup)
    os.replace(src=program, dst=backup)

    try:
        shutil.move(src=str(new), dst=str(program))

    except OSError:
        os.replace(src=backup, dst=program)
        raise


def restart_program() -> None:
    program = program_path()

    if sys.platform == "darwin":
        subprocess.Popen(args=["open", "-n", str(program)])

        return

    # The new process must unpack its own bundle, not inherit this one's.
    subprocess.Popen(args=[str(program)], env={**system_env(), "PYINSTALLER_RESET_ENVIRONMENT": "1"})


def open_in_system(path: Union[Path, str]) -> None:
    if sys.platform == "win32":
        os.startfile(filepath=path)

    elif sys.platform == "darwin":
        subprocess.Popen(args=["open", str(path)])

    else:
        subprocess.Popen(
            args=["xdg-open", str(path)],
            env=system_env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def system_env() -> Dict[str, str]:
    # Desktop tools must not inherit the bundled library path of a packaged build.
    env = os.environ.copy()
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)

    if original is not None:
        env["LD_LIBRARY_PATH"] = original

    elif getattr(sys, "frozen", False):
        env.pop("LD_LIBRARY_PATH", None)

    return env
