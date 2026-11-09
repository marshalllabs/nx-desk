#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Iterable, Optional

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nx_desk import config as settings
from nx_desk import system

NAME = settings.PROGRAM_NAME
DIST = ROOT / "dist"
WORK = DIST / "work"
DATA_FOLDERS = ("downloaded", "covers")
BUNDLED_PACKAGES = ("certifi", "pyinstaller")
LICENSE_FILE = re.compile(pattern=r"licen[cs]e|copying|notice", flags=re.IGNORECASE)


def write_build_config() -> Path:
    config = settings.load_config()
    missing = [key for key in settings.CONFIG_KEYS if not config.get(key)]

    if missing:
        sys.exit(f"Missing configuration: {', '.join(missing)} (see .env.example)")

    values = {key: config[key] for key in settings.CONFIG_KEYS}
    values.update({key: config[key] for key in settings.OPTIONAL_KEYS if config.get(key)})
    values[settings.VERSION_KEY] = os.environ.get(key=settings.VERSION_KEY, default="")
    generated = WORK / "generated"
    generated.mkdir(parents=True)
    (generated / "nx_desk_build_config.py").write_text(data=f"VALUES = {values!r}\n", encoding="utf-8")

    return generated


def compile_app(generated: Path) -> None:
    args = [
        "--noconfirm",
        "--log-level",
        "WARN",
        "--windowed",
        "--name",
        NAME,
        "--paths",
        str(generated),
        "--hidden-import",
        "nx_desk_build_config",
        "--exclude-module",
        "tkinter",
        "--collect-data",
        "certifi",
        "--add-data",
        f"{ROOT / 'nx_desk' / 'ui' / 'icon.png'}{os.pathsep}nx_desk/ui",
        "--add-data",
        f"{ROOT / 'nx_desk' / 'ui' / 'icons'}{os.pathsep}nx_desk/ui/icons",
        "--distpath",
        str(WORK / "output"),
        "--workpath",
        str(WORK / "pyinstaller"),
        "--specpath",
        str(WORK),
    ]

    # macOS needs a folder-based .app; a one-file binary inside an .app is deprecated.
    if sys.platform != "darwin":
        args.append("--onefile")

    # Linux has no icon inside the binary; the window icon comes from icon.png.
    if sys.platform in ("darwin", "win32"):
        args += ["--icon", str(ROOT / "assets" / ("icon.icns" if sys.platform == "darwin" else "icon.ico"))]

    PyInstaller.__main__.run(pyi_args=[*args, str(ROOT / "main.py")])


def read_python_license() -> Optional[str]:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    prefix = Path(sys.base_prefix)

    return first_text(paths=[prefix / "lib" / version / "LICENSE.txt", prefix / "LICENSE.txt", prefix / "LICENSE"])


def first_text(paths: Iterable[Path]) -> Optional[str]:
    return next((path.read_text(encoding="utf-8", errors="replace") for path in paths if path.is_file()), None)


def read_package_licenses(name: str) -> Optional[str]:
    distribution = metadata.distribution(distribution_name=name)
    files = [
        file
        for file in distribution.files or []
        if ".dist-info" in str(file) and LICENSE_FILE.search(string=Path(file).name)
    ]
    texts = [
        Path(str(distribution.locate_file(path=file))).read_text(encoding="utf-8", errors="replace") for file in files
    ]

    return "\n\n".join(texts) or None


def third_party_licenses() -> str:
    # Qt and PySide6 are under the LGPL; their texts come with the PySide6 package.
    sections = [("Python", read_python_license(), "https://docs.python.org/3/license.html")]
    sections += [
        (name, read_package_licenses(name=name), f"https://pypi.org/project/{name}/") for name in BUNDLED_PACKAGES
    ]
    # The PySide6 wheels carry no license text, so Qt's LGPL comes from licenses/.
    sections += [
        (
            "Qt and PySide6, under the GNU LGPL 3.0 (source at https://code.qt.io)",
            first_text(paths=[ROOT / "licenses" / "lgpl-3.0.txt"]),
            "https://www.gnu.org/licenses/lgpl-3.0.txt",
        ),
        (
            "GNU GPL 3.0, which the LGPL builds on",
            first_text(paths=[ROOT / "licenses" / "gpl-3.0.txt"]),
            "https://www.gnu.org/licenses/gpl-3.0.txt",
        ),
    ]
    parts = ["NX Desk's packaged builds include the software below. Its own license is in LICENSE."]

    for name, text, url in sections:
        if text is None:
            print(f"warning: license text of {name} not found, linking to it instead")

        parts.append(f"{'=' * 78}\n{name}\n{'=' * 78}\n\n{text or f'See {url}'}")

    return "\n\n".join(parts) + "\n"


def stage(package: str) -> Path:
    target = DIST / package
    target.mkdir()
    output = WORK / "output"

    if sys.platform == "darwin":
        subprocess.run(args=["ditto", str(output / f"{NAME}.app"), str(target / f"{NAME}.app")], check=True)

    else:
        binary = f"{NAME}.exe" if sys.platform == "win32" else NAME
        shutil.move(src=str(output / binary), dst=str(target / binary))

    for folder in DATA_FOLDERS:
        (target / folder).mkdir()

    shutil.copy(src=ROOT / "LICENSE", dst=target / "LICENSE")
    (target / "THIRD_PARTY_LICENSES.txt").write_text(data=third_party_licenses(), encoding="utf-8")

    return target


def archive(source: Path) -> Path:
    target = source.with_suffix(suffix=".zip")

    if sys.platform == "darwin":
        # ditto keeps the symlinks and signature inside the .app.
        subprocess.run(args=["ditto", "-c", "-k", str(source), str(target)], check=True)

        return target

    with zipfile.ZipFile(file=target, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(source.rglob(pattern="*")):
            output.write(path, path.relative_to(source))

    return target


def main() -> None:
    shutil.rmtree(path=DIST, ignore_errors=True)
    compile_app(generated=write_build_config())
    target = archive(source=stage(package=Path(system.asset_name()).stem))
    shutil.rmtree(path=WORK)
    print(target)


if __name__ == "__main__":
    main()
