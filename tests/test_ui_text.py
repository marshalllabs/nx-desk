import unittest
from typing import Set

from nx_desk.schemas.presentation import DownloadChoice, DownloadChoices, VersionCells
from nx_desk.schemas.snapshot import ModRow
from nx_desk.ui import rows
from nx_desk.ui.rows import (
    action_text,
    download_scopes,
    picked_text,
    progress_of,
    release_labels,
    repo_labels,
)
from nx_desk.ui.theme import status_matches
from nx_desk.utils.text import again, few_names, plural
from tests.helpers import job, row


class RowTextTests(unittest.TestCase):
    def item(self, **fields: object) -> ModRow:
        base = {"job": None, "status": "update", "version": "1.0.1", "local_version": "1.0.0", "remote": False}

        return row(**{**base, "game_version": "1.0.2", "local_game_version": "1.0.1", **fields})

    def test_an_update_shows_old_and_new_in_the_columns_that_change(self) -> None:
        self.assertEqual(
            first=rows.version_cells(item=self.item()),
            second=VersionCells(mod="1.0.0 → 1.0.1", game="1.0.1 → 1.0.2"),
        )
        self.assertEqual(
            first=rows.version_cells(item=self.item(local_version="1.0.1")),
            second=VersionCells(mod="1.0.1", game="1.0.1 → 1.0.2"),
        )
        self.assertEqual(first=rows.status_text(item=self.item()), second="Update available")
        self.assertEqual(
            first=rows.update_text(item=self.item()),
            second="Update available: mod 1.0.0 → 1.0.1, game 1.0.1 → 1.0.2",
        )

    def test_rows_without_an_update_show_one_value(self) -> None:
        self.assertEqual(
            first=rows.version_cells(item=self.item(status="ok")),
            second=VersionCells(mod="1.0.1", game="1.0.2"),
        )
        self.assertEqual(
            first=rows.version_cells(item=self.item(status="ok", game_version="")),
            second=VersionCells(mod="1.0.1", game="Miss"),
        )
        self.assertEqual(first=rows.status_text(item=self.item(status="ok", remote=True)), second="Online only")
        self.assertEqual(first=rows.status_text(item=self.item(status="missing")), second="Not downloaded")

    def test_a_running_job_shows_its_progress(self) -> None:
        running = job(phase="downloading", done=50, total=200)
        self.assertEqual(first=rows.status_text(item=self.item(job=running)), second="25%")
        self.assertEqual(
            first=rows.status_text(item=self.item(job=running.model_copy(update={"phase": "waiting_repack"}))),
            second="Waiting to repack",
        )
        self.assertEqual(
            first=rows.status_text(item=self.item(job=running.model_copy(update={"phase": "waiting_limit"}))),
            second="Waiting for the server",
        )
        self.assertEqual(
            first=rows.row_tag(item=self.item(job=running.model_copy(update={"phase": "error"}))),
            second="error",
        )

    def test_sort_titles_and_counts(self) -> None:
        order = rows.SortState(column="name")
        self.assertEqual(first=order.title(column="name", text="Name"), second="Name ▲")
        order.toggle(column="name")
        self.assertEqual(first=order.title(column="name", text="Name"), second="Name ▼")
        self.assertEqual(first=order.title(column="size", text="Size"), second="Size")
        self.assertEqual(first=(plural(count=1, word="mod"), plural(count=2, word="mod")), second=("1 mod", "2 mods"))
        self.assertEqual(first=few_names(names=["a", "b"]), second="a, b")
        self.assertEqual(first=few_names(names=["a", "b", "c", "d", "e"]), second="a, b, c and 2 more")
        self.assertEqual(
            first=(rows.format_time(seconds=42), rows.format_time(seconds=125), rows.format_time(seconds=3720)),
            second=("42s", "2m 5s", "1h 2m"),
        )


class StatusFilterTests(unittest.TestCase):
    def shown(self, *names: str) -> Set[str]:
        items = {
            "new": row(status="missing", remote=False),
            "update": row(status="update", remote=False),
            "saved": row(status="ok", remote=False),
            "cloud": row(status="ok", remote=True),
            "cloud_update": row(status="update", remote=True),
        }

        return {key for key, item in items.items() if status_matches(item=item, picked=set(names))}

    def test_each_filter_shows_its_rows(self) -> None:
        self.assertEqual(first=len(self.shown()), second=5)
        self.assertEqual(first=self.shown("new"), second={"new"})
        self.assertEqual(first=self.shown("update"), second={"update", "cloud_update"})
        self.assertEqual(first=self.shown("downloaded"), second={"update", "saved"})
        self.assertEqual(first=self.shown("online"), second={"cloud", "cloud_update"})

    def test_several_filters_show_rows_matching_any(self) -> None:
        self.assertEqual(first=self.shown("new", "online"), second={"new", "cloud", "cloud_update"})
        self.assertEqual(first=self.shown("new", "update", "downloaded", "online"), second=self.shown())

    def test_mod_rows_show_versions_and_total(self) -> None:
        update = row(
            name="B",
            version="2.0",
            local_version="1.0",
            game_version="1.1.0",
            local_game_version="1.0.0",
            status="update",
            size=2048,
        )
        fresh = row(name="A", version="", local_version="", game_version="", status="missing", size=0)

        table = rows.mod_rows(items=[update, fresh])
        columns = table.columns
        found = table.rows
        total = table.total
        self.assertEqual(first=columns, second=("Game", "Mod version", "Game version", "Size"))
        self.assertEqual(first=found[0][0], second="B")
        self.assertIn(member="→", container=found[0][1])
        self.assertEqual(first=found[1][3], second="-")
        self.assertTrue(expr=total.startswith("Total "))
        self.assertEqual(first=rows.mod_rows(items=[fresh]).total, second="")

    def test_button_names_one_pick_and_counts_several(self) -> None:
        self.assertEqual(first=picked_text(title="Status", picked=[]), second="Status")
        self.assertEqual(first=picked_text(title="Status", picked=["New"]), second="Status: New")
        self.assertEqual(first=picked_text(title="Status", picked=["New", "Update"]), second="Status (2)")


class ChoiceLabelTests(unittest.TestCase):
    def test_repositories_show_their_name_unless_two_share_it(self) -> None:
        labels = repo_labels(repos=["me/mods", "me/tools", "org/tools"])
        self.assertEqual(first=labels, second={"me/mods": "mods"})

    def test_the_latest_release_is_marked(self) -> None:
        self.assertEqual(first=release_labels(latest="v2"), second={"v2": "v2  (latest)"})
        self.assertEqual(first=release_labels(latest=""), second={})


class AgainTests(unittest.TestCase):
    def test_work_done_before_gets_the_re_prefix(self) -> None:
        self.assertEqual(first=again(text="Download all", done=True), second="Re-download all")
        self.assertEqual(first=again(text="Upload", done=True), second="Re-upload")
        self.assertEqual(first=again(text="Upload", done=False), second="Upload")
        self.assertEqual(first=again(text="", done=True), second="")


class ProgressTests(unittest.TestCase):
    def test_a_download_shows_how_much_arrived(self) -> None:
        self.assertEqual(first=progress_of(item=row(job=job(phase="downloading", done=35, total=100))), second=0.35)

    def test_an_upload_shows_how_much_was_sent(self) -> None:
        self.assertEqual(first=progress_of(item=row(job=job(phase="uploading", sent=50, total=100))), second=0.5)

    def test_other_phases_and_unknown_sizes_show_no_bar(self) -> None:
        self.assertEqual(first=progress_of(item=row(job=job(phase="queued", total=100))), second=-1.0)
        self.assertEqual(first=progress_of(item=row(job=job(phase="error", total=100))), second=-1.0)
        self.assertEqual(first=progress_of(item=row(job=job(phase="downloading", total=0))), second=-1.0)

    def test_a_row_without_a_job_shows_no_bar_and_a_full_download_stops_at_one(self) -> None:
        self.assertEqual(first=progress_of(item=row()), second=-1.0)
        self.assertEqual(first=progress_of(item=row(job=job(phase="downloading", done=130, total=100))), second=1.0)


class DownloadScopesTests(unittest.TestCase):
    NEW, DONE = ["n1", "n2"], ["o1", "o2", "o3"]

    def scopes(self, picked: int) -> DownloadChoices:
        return download_scopes(
            picked=picked,
            new=self.NEW,
            done=self.DONE,
            picked_new=["pn"],
            picked_done=["pd1", "pd2"],
        )

    def test_with_no_game_picked_the_buttons_take_the_whole_catalog(self) -> None:
        self.assertEqual(
            first=self.scopes(picked=0),
            second=DownloadChoices(
                download=DownloadChoice(label="Download all", ids=self.NEW),
                redownload=DownloadChoice(label="Re-download all", ids=self.DONE),
            ),
        )

    def test_with_one_game_picked_they_still_take_the_whole_catalog(self) -> None:
        self.assertEqual(
            first=self.scopes(picked=1),
            second=DownloadChoices(
                download=DownloadChoice(label="Download all", ids=self.NEW),
                redownload=DownloadChoice(label="Re-download all", ids=self.DONE),
            ),
        )

    def test_with_several_picked_they_take_those(self) -> None:
        choices = self.scopes(picked=2)
        download = choices.download
        redownload = choices.redownload
        self.assertEqual(first=download, second=DownloadChoice(label="Download selected", ids=["pn"]))
        self.assertEqual(first=redownload, second=DownloadChoice(label="Re-download selected", ids=["pd1", "pd2"]))
        self.assertEqual(first=self.scopes(picked=40).download.label, second="Download selected")

    def test_a_button_with_nothing_to_take_has_no_mods(self) -> None:
        choices = download_scopes(picked=3, new=[], done=[], picked_new=[], picked_done=["x"])
        download = choices.download
        redownload = choices.redownload
        self.assertEqual(first=(download.ids, redownload.ids), second=([], ["x"]))


class ActionTextTests(unittest.TestCase):
    def test_count_and_size_share_one_label(self) -> None:
        self.assertEqual(first=action_text(text="Download", count=4, size=3 * 1024**2), second="Download (4 · 3.0 MiB)")
        self.assertEqual(first=action_text(text="Download all", count=1200, size=0), second="Download all (1,200)")
        self.assertEqual(first=action_text(text="Upload", count=0), second="Upload")
