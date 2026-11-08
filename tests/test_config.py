import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from nx_desk import config as settings
from nx_desk import names, vault


class ConfigTests(unittest.TestCase):
    def test_reads_dotenv_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(data='# comment\n\nA=1\nB = "two=2"\nC=\n', encoding="utf-8")
            self.assertEqual(settings.parse_dotenv(path=path), {"A": "1", "B": "two=2", "C": ""})

    def test_user_agent_defaults_to_a_neutral_token(self) -> None:
        with (
            mock.patch.object(settings, "parse_dotenv", return_value={}),
            mock.patch.dict(os.environ, {}, clear=True),
        ):
            self.assertEqual(settings.user_agent(), "Mozilla/5.0")

    def test_user_agent_can_be_configured(self) -> None:
        with (
            mock.patch.object(settings, "parse_dotenv", return_value={}),
            mock.patch.dict(os.environ, {settings.USER_AGENT_KEY: "Agent/2"}),
        ):
            self.assertEqual(settings.user_agent(), "Agent/2")

    def test_environment_overrides_dotenv(self) -> None:
        with (
            mock.patch.object(settings, "parse_dotenv", return_value={"NX_DESK_RELEASES_URL": "file"}),
            mock.patch.dict(os.environ, {"NX_DESK_RELEASES_URL": "env", "OTHER": "x"}),
        ):
            config = settings.load_config()

        self.assertEqual(config["NX_DESK_RELEASES_URL"], "env")
        self.assertNotIn("OTHER", config)


class PlatformTests(unittest.TestCase):
    def frozen_base(self, platform: str, executable: str) -> Path:
        with (
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "platform", platform),
            mock.patch.object(sys, "executable", executable),
            mock.patch.object(os, "access", return_value=True),
        ):
            return settings.base_dir()

    def test_source_runs_use_the_data_folder(self) -> None:
        self.assertEqual(settings.base_dir(), Path(settings.__file__).resolve().parents[1] / ".data")

    def test_data_sits_next_to_the_program(self) -> None:
        self.assertEqual(self.frozen_base(platform="linux", executable="/opt/vault/App"), Path("/opt/vault"))

    def test_macos_uses_the_folder_holding_the_app(self) -> None:
        self.assertEqual(
            self.frozen_base(platform="darwin", executable="/Users/a/Games/App.app/Contents/MacOS/App"),
            Path("/Users/a/Games"),
        )

    def test_macos_translocated_app_uses_application_support(self) -> None:
        result = self.frozen_base(
            platform="darwin",
            executable="/private/var/AppTranslocation/X/d/App.app/Contents/MacOS/App",
        )
        self.assertEqual(result.parts[-3:], ("Library", "Application Support", "NXDesk"))


class SizeUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.addCleanup(names.set_size_units, names.BINARY)

    def test_binary_is_the_default_and_decimal_can_be_chosen(self) -> None:
        self.assertEqual(names.format_size(value=3 * 1024**3), "3.00 GiB")
        self.assertEqual(names.format_size(value=1536 * 1024), "1.5 MiB")
        self.assertEqual(names.format_size(value=2048), "2 KiB")
        names.set_size_units(units="decimal")
        self.assertEqual(names.format_size(value=3_000_000_000), "3.00 GB")
        self.assertEqual(names.format_size(value=1_500_000), "1.5 MB")

    def test_the_choice_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            vault.Vault(base=folder).set_size_units(units="decimal")
            self.assertEqual(vault.Vault(base=folder).size_units, "decimal")
            self.assertEqual(names.format_size(value=2000), "2 KB")


class FontSettingTests(unittest.TestCase):
    def test_the_default_font_is_empty_and_a_choice_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            store = vault.Vault(base=folder)
            self.assertEqual((store.font_family, store.font_size), ("", 0))
            store.set_font(family=" Fira Sans ", size=12)
            self.assertEqual(
                (vault.Vault(base=folder).font_family, vault.Vault(base=folder).font_size),
                ("Fira Sans", 12),
            )
            store.set_font(family="", size=-3)
            self.assertEqual((vault.Vault(base=folder).font_family, vault.Vault(base=folder).font_size), ("", 0))


class LogFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = vault.Vault(base=self.temp.name)

    def text(self) -> str:
        return "".join(path.read_text(encoding="utf-8") for path in self.store.logs_dir.glob("*.log"))

    def test_lines_of_both_logs_reach_the_file(self) -> None:
        self.store._log_download(text="saved", level="ok", game="Game")
        self.store._log_github(text="line one\nline two", level="error")
        lines = self.text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^\d\d:\d\d:\d\d OK +download +Game: saved$")
        self.assertTrue(lines[1].endswith("line one line two"))
        self.assertIn("ERROR", lines[1])

    def test_a_log_file_that_cannot_be_written_is_not_an_error(self) -> None:
        self.store.logs_dir.write_text(data="in the way", encoding="utf-8")
        self.store._log_download(text="saved")
        self.assertEqual(self.store.snapshot().log[-1][3], "saved")

    def test_old_files_go_and_recent_ones_stay(self) -> None:
        self.store.logs_dir.mkdir()
        old, recent = self.store.logs_dir / "nx-desk-2020-01-01.log", self.store.logs_dir / "nx-desk-x.log"
        old.touch()
        recent.touch()
        moment = time.time() - settings.LOG_MAX_AGE - 60
        os.utime(path=old, times=(moment, moment))
        self.store._prune_logs()
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
