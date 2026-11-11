# NX Desk

- A desktop app for downloading, tracking and repackaging Nintendo Switch mods.
- Add catalogs you trust. NX Desk ships without a catalog.

## Features

- Separate downloads, artwork and status for each catalog.
- Resumable downloads with mirrors, SHA-256 checks and update detection.
- Consistent mod ZIPs with configurable compression.
- GitHub release uploads and downloads.
- Read-only scanning of Switch SD mod content.

## Install

- Download the ZIP for your platform from [Releases](../../releases), extract it and launch NX Desk.
- NX Desk stores its data beside the app. Move the whole folder to keep that data.

| Platform | Notes |
| --- | --- |
| Windows | SmartScreen may warn on first launch. |
| macOS | The app is not notarized. Run `xattr -dr com.apple.quarantine NXDesk.app` if needed. |
| Linux | Requires glibc 2.35 or later. |

## Usage

| Tab | What to do |
| --- | --- |
| Catalog | Add a catalog by HTTPS URL, set a mod name under **Saving**, then select mods to download. |
| Switch SD | Mount a CFW SD card to browse mod content and copy Title IDs. |
| Switch Ports | Browse ports and emulators. |
| Homebrews | Search and filter homebrew apps, then open their source pages. |
| Title IDs | Look up games, system titles and sysmodules by name or ID. |
| GitHub | Set a personal access token in **Settings**, then select a release to upload, download or compare assets. |
