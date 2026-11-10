# NX Desk

- A desktop app that downloads, tracks and repackages game mods, and keeps them on GitHub releases.

- Works with catalogs you add yourself; none is included.
- Catalogs are not signed, so only add ones you trust.

## Features

- Several catalogs, each with its own downloads, art and state.
- Resumable downloads with mirrors, SHA-256 checks and update detection.
- Every mod repacked into one layout, at the compression level you choose.
- Upload to and download from GitHub releases through the GitHub REST API.
- Ports, Homebrews and Title IDs lists.
- Updates itself from public GitHub releases; the release repository must be public for update checks and downloads.

## Install

- Download the zip for your platform from [Releases](../../releases) and extract it anywhere.
- The app keeps its data next to itself, so move the folder as a whole.

| Platform | Notes                                                          |
| -------- | -------------------------------------------------------------- |
| Windows  | Not code signed, so SmartScreen may warn on first launch       |
| macOS    | Not notarized; run `xattr -dr com.apple.quarantine NXDesk.app` |
| Linux    | Needs glibc 2.35 or newer                                      |

## Usage

1. Click the catalog button → add a catalog by name and HTTPS URL.
2. Enter a **Mod name** under **Saving**, such as the language or the author. It is part of every saved path.
3. Download one game, a selection or everything. **Stop all** ends every download.

```
<destination or downloaded/>/<catalog>/
└── <Game> - [<mod name>] - [<game version>]/
    └── <Game> - [<mod name>] - [<game version>].zip
        └── contents/<title id>/...
```

- A game counts as downloaded when its folder holds that zip.
- **Download** takes new games, **Re-download** the downloaded ones; with several rows selected, only those.
- **Upload to GitHub** sends each finished mod to the release named after the catalog folder.
   - **Delete local copy** removes it from disk once the release records it.
- Search, **Genres** and **Status** filter the list; ≡ switches between **List** and **Grid**.
- Editing a catalog's **Name** also renames its folder and, with a configured GitHub token, its release.
- **Settings** (Ctrl+,): font, compression, size units, SteamGridDB key, GitHub token, notifications, log folder.
- Keys: Ctrl+Q quits, Ctrl+PgUp/PgDown switches tabs, Ctrl+F searches.

## GitHub tab

- Moves mod folders between a source folder and a GitHub release, using a personal access token saved in the system keyring.
- A mod folder is `<Game> - [<mod>] - [<version>]` and holds a zip of the same name.
- Zips over 2 GB are split into parts and joined again on download.
- Uploads replace the old file; the app keeps no backups.
- Every delete asks you to type a word first.
- **Compare** shows the chosen release beside another one.
- **Retry** runs the last failed upload or download again.
- **Delete after upload** removes each source folder once its upload is recorded.

## GitHub authentication

- In **Settings > GitHub**, paste a personal access token and select **Apply** or **Save**.
- Use a fine-grained PAT for the destination owner and repositories with **Contents: Read and write**.
- Organization repositories may require owner approval; a pending or expired token cannot upload.
- Public repositories and releases can remain readable even when not selected for the PAT.
- Seeing a repository in the picker does not mean the token can write to it; writes require access to that repository.
- Tokens stay in the system keyring; settings store only whether one is saved.
- Unlock or enable the system keyring if saving fails; tokens have no plaintext or file-based fallback.
- Use **Remove** and apply to forget the token. Saved tokens are never displayed in Settings.
- GitHub CLI is no longer required; existing CLI authentication is not imported.

## Release state

- NX Desk and NX Index follow the same [release state contract](docs/release-state.md).
- Automatic uploads, manual uploads and recovered records write the original checksum and game version.
- Original checksum equality takes priority over version metadata; legacy missing fields do not force downloads.
- Without matching checksum fields, use mod versions and known game versions as a fallback.
- Metadata repairs preserve uploaded files, their folder and upload time; IDs sharing a file keep their own records.
- Missing recorded assets count as missing uploads; invalid remote state is never replaced with empty state.
- Refresh release state to see changes made by the other application; use one writer per release.

## Other tabs

- **Switch Ports**: ports and emulators, as a list or a grid, from `NX_DESK_PORTS_URL`.
- **Homebrews**: searchable List/Grid view with group and type filters, metadata, sorting and
  detail-page links, from `NX_DESK_HOMEBREWS_URL`. Refresh clears search and filters; a failed fetch
  keeps the last cached list. This tab opens source pages for download and installation details.
  - Uses the shared artwork key for grid covers and detail banners. Images are requested for the
    selected and visible entries; unmatched entries keep their default icon.
- **Title IDs**: looks up a title ID or name among games, system titles and sysmodules, from `NX_DESK_TITLE_IDS_URL`.
- **Game art** comes from SteamGridDB when you set its API key in **Settings**; the key is kept in the system keyring.

## Catalog format

- The smallest catalog is a `mods` list with an `id` and an HTTPS `url` for each mod.
- Other field names also work, or map them by hand.
- The catalog button → **Catalog format** lists the names read and shows a template.

## Configuration

- Builds embed these values; from source, set them in `.env` (see `.env.example`). Real environment variables win.

| Variable                | Description                                             |
| ----------------------- | ------------------------------------------------------- |
| `NX_DESK_RELEASES_URL`  | GitHub API URL of the latest release, for update checks |
| `NX_DESK_TITLE_IDS_URL` | Link to the `title_ids.json` list                       |
| `NX_DESK_PORTS_URL`     | Optional link to the `switch-ports.json` list           |
| `NX_DESK_HOMEBREWS_URL` | Optional link to the `homebrews.json` list from NX Index |
| `NX_DESK_USER_AGENT`    | Optional User-Agent; blank uses `Mozilla/5.0`           |

## Development

- Python 3.12 and [uv](https://docs.astral.sh/uv/).
- On Linux under X11, Qt also needs `libxcb-cursor0` (Debian/Ubuntu) or `xcb-util-cursor` (Arch).
- From source, data lives in `.data/`, which git ignores.

```bash
make run     # run from source
make check   # print available updates, no GUI
make test    # run isolated offline tests
make lint    # ruff, formatting, mypy and pyright
make format  # fix style
make build   # build dist/NXDesk-<platform>-<arch>.zip
make clean   # remove build output and project caches; keep .venv
```

## Releases

- Pushing to `main` runs semantic-release on Conventional Commits:
   - `fix:` is a patch, `feat:` a minor, `feat!:` a major release.
   - `docs:`, `chore:`, `refactor:` and `test:` release nothing.
- The workflow builds four zips and publishes the release once all are attached.
- Packaged apps check for a new release at startup and every 30 minutes.
