from ... import uploader
from ...names import format_size
from ...schemas.github import UploadSnapshot
from ..dialogs import show_message
from ..repo_picker import show_repo
from ..rows import format_time, release_labels
from ..theme import COLORS
from ..widgets.basics import fill_choices, run_bar
from .compare_view import CompareView
from .trees import Trees


class Painting(CompareView, Trees):
    def paint_transfer(self, job: UploadSnapshot) -> None:
        moving = job.transfer
        loading = not moving and job.phase not in ("idle", "uploading")
        run_bar(bar=self.progress, loading=loading)
        # Like the Catalog tab: the row says nothing while no job runs, so it only shows then.
        self.progress_row.setVisible(loading or bool(moving) or job.phase == "uploading")

        if loading:
            self.spinner.start(text="Working with GitHub…")

            return

        self.spinner.stop()

        if moving:
            fraction = moving.done / max(1, moving.total)
            parts = [
                moving.label,
                f"{100 * fraction:.0f}%",
                f"{format_size(value=moving.done)} of {format_size(value=moving.total)}",
            ]

            if moving.speed > 0:
                parts.append(f"{format_size(value=moving.speed)}/s")
                parts.append(f"{format_time(seconds=(moving.total - moving.done) / moving.speed)} left")

            self.progress.setValue(int(1000 * fraction))
            self.progress_label.setText(" · ".join(parts))
        elif job.phase == "uploading":
            self.progress.setValue(int(1000 * job.done / max(1, job.total)))
            self.progress_label.setText(f"Working {job.done}/{job.total}")
        else:
            self.progress.setValue(0)
            self.progress_label.setText("")

    def paint(self, job: UploadSnapshot) -> None:
        self.log.paint(lines=job.log)

        if job.source_list != self.shown_source:
            self.shown_source = job.source_list

            if job.source != self.source.text():
                self.source.setText(job.source)

        key = (
            job.phase,
            job.tree,
            job.done,
            job.message,
            job.failed,
            job.runs,
            job.alerts,
            job.release_list,
            job.repo_list,
            job.asset_list,
            tuple((folder.name, folder.status, folder.progress) for folder in job.folders),
            tuple(job.item_progress.items()),
            tuple(dict(job.transfer).values()) if job.transfer else (),
            job.compare_list,
            (job.retry_kind, tuple(job.retry_names), job.retry_tag),
        )

        if key == self.painted:
            return

        self.painted = key
        busy = job.phase != "idle"

        for action in (self.scan_action, self.refresh_action, self.recompare_action):
            action.setEnabled(not busy)

        self.compare_button.setEnabled(not busy)

        # Routine scan and release counts live in the panel titles; errors still need a message.
        loading = busy and job.phase != "uploading"
        self.status.setText(job.message if job.failed and not loading else "")
        self.status.setVisible(bool(self.status.text()))
        self.status.setStyleSheet(f"color: {COLORS['bad' if job.failed else 'muted']};")

        if job.repo_list != self.shown_repos:
            self.shown_repos = job.repo_list
            show_repo(widget=self.repo_button, repo=self.repo, repos=job.repos)

        if job.release_list != self.shown_releases:
            self.shown_releases = job.release_list
            self.known_releases = job.releases
            self.latest_release = job.latest_release
            labels = release_labels(latest=job.latest_release)
            fill_choices(box=self.release_box, choices=job.releases, current=job.select_tag, labels=labels)
            self.save()
            self.fill_compare_box()

        self.retry_job = (job.retry_kind, list(job.retry_names), job.retry_tag)
        self.cancel_button.setVisible(job.phase == "uploading")
        self.paint_transfer(job=job)
        assets = {asset.name: asset for asset in job.assets}
        local_assets = {
            uploader.parts.group_key(name=name)
            for folder in job.folders
            for name in uploader.parts.owned_assets(stem=folder.asset.removesuffix(".zip"), assets=assets)
        }
        uploaded_folders = self.uploaded_folders(job=job)
        self.paint_assets(job=job, local_assets=local_assets)
        self.paint_rows(job=job, uploaded_folders=uploaded_folders)
        self.update_legend(job=job, local_assets=local_assets)
        self.paint_compare(job=job)
        self.paint_choice()

        if job.alerts != self.reported_alerts:
            self.reported_alerts = job.alerts
            self.app.later(show_message, "GitHub", job.message, self.app)

        if job.runs != self.reported_runs:
            self.reported_runs = job.runs
            self.app.notify(title="GitHub", text=job.message)
            self.app.later(show_message, "Upload", job.message, self.app)
