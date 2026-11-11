# NX Desk guidelines

## Workspace context

- Follow the suite guidance in `../AGENTS.md`.
- Keep repository guidance here and user guidance in README. Do not recreate `docs/`.
- Keep source-specific catalog mapping in nx-index; check both projects before changing their contract.

## Commands

- Run from the repository root with `uv`; the app supports Python 3.12.
- Dependencies are declared in `pyproject.toml` and pinned in `uv.lock`; dev and build groups are installed by default.
- After changing dependencies, run `uv lock` and include the lockfile in the reviewed change.

| Command | Purpose |
| --- | --- |
| `make install` | Sync locked dependencies into `.venv/` and install hooks |
| `make run` | Launch the PySide6 app |
| `make check` | Print mod updates without opening the GUI |
| `make test` | Run unit tests |
| `make lint` | Ruff, formatting, mypy and Pyright |
| `make format` | Apply style fixes and formatting |
| `make build` | Build `dist/NXDesk-<platform>-<arch>.zip` |
| `make clean` | Remove build output and project bytecode caches; preserve `.venv/` and `.data/` |
| `.venv/bin/python -B -m tests.run tests.github.test_uploads` | Run one test module |

## Code map

- `main.py` is the packaged entry point; `python -m nx_desk` also works.
- Paths below are relative to the `nx_desk/` package.

| Path | Responsibility |
| --- | --- |
| `utils/` | Small reusable project helpers, one file per topic |
| `schemas/` | Shared Pydantic models and aliases, grouped by area |
| `config.py`, `net.py`, `system.py` | Configuration, HTTP and OS-specific operations |
| `credentials.py`, `steamgriddb.py` | Secret storage and artwork service access |
| `names.py`, `zips.py` | Names, saved paths and archive repackaging |
| `catalog/` | Untrusted catalog parsing and reference-list readers |
| `switch_sd/` | Read-only CFW card detection, content scanning and metadata verification |
| `uploader/` | GitHub REST requests, releases, transfers, parts and release state |
| `vault/` | Application state and jobs, split into mixins |
| `cli.py` | Startup and background check loop |
| `ui/` | PySide6 app, tabs and shared widgets |

## Python and module boundaries

- Use four spaces, a 120-character target, `snake_case` names and `PascalCase` classes.
- Use short comments when needed; do not add docstrings.
- Use `model_copy(update=...)` to copy model values with changes.
- Mutable job/state models use `validate_assignment`; persisted models use `Vault._load_model` and `TypeAdapter`.
- Use `cast` only after checking the value, with a reason.
- Preserve parameter names in test fakes.
- Use one item per line and trailing commas in multiline brackets.
  - Ruff's `COM812` formatter warning is expected.
- Import names from their defining modules; use `TYPE_CHECKING` for type-only cycles.
- Keep `__init__.py` empty except for the existing `vault` mixin assembly and `uploader` module imports.
- Call patchable dependencies through their modules: `net.http_get`, `settings.load_config`, `uploader.api.request`.
- Keep Qt imports inside the UI boundary; `cli.main` imports the UI lazily.
  - CLI checks and tests must work without Qt; CI lacks the libraries needed to load PySide6.
- `vault/base.py` owns shared attributes; mixins inherit the dependencies they call.
- Split tab widgets by responsibility; `state.py` declares attributes and `tab.py` assembles mixins.

## Threads and jobs

- Network work runs in worker threads; never update Qt widgets directly from those threads.
- The UI polls vault snapshots through `App.refresh`; expose new state in snapshots and paint it in the tab.
- Use `App.later` when a worker must request a UI action.
- Guard shared vault state with `self.lock`; perform network calls outside it and recheck state afterwards.
- Downloads and repacking use separate queues; preserve per-part and per-target locks.
- Each run owns its cancel event; stopped workers must not modify a later run of the same mod.
- Active catalog paths change at runtime; preserve busy checks around catalog switches and additions.

## Catalogs, archives and release state

- Catalog aliases and user mappings stay supported; only an ID and an HTTPS URL are required.
- SHA-256 and size are optional; keep version-based fallback when checksums are absent.
- Keep catalog protection removed; ordinary links, optional checksums and generic HTTP 429 waiting remain.
- Preserve archive limits and every title ID folder when repackaging to `contents/<title id>/...`.
- Download records store the original download's SHA-256, not the repacked ZIP's checksum.
- Entries sharing a file share a download and saved folder; record every twin after completion.
- Disk contents determine whether a mod exists locally; records identify its release.
- Linked release `state.json` writes run under `github_lock`, read first and replace through a temporary asset.
- Apply the shared release-state contract to records recovered from existing assets.
- Delete a local copy only after its upload and release-state write succeed.
- Local deletion must stay below the source folder, never delete that folder or its ancestors.
- Preserve typed confirmations for destructive operations and rollback on failed linked catalog/release renames.
- GitHub operations use REST with a PAT stored only in the system keyring; registry stores presence only.
  - API requests send tokens only to the API host; uploads send them only to `UPLOAD_HOST`.
  - Asset redirects never forward tokens to storage hosts; never import credentials from `gh`.
  - Repository visibility and public read access do not prove token write permissions.
- Preserve split/join support for files over 2 GB and restrict automatic retries to safe operations.

## Switch SD

- Keep Qt mount enumeration under `ui/switch_sd/` and filesystem work under `switch_sd/`.
- Scan only supported mounted volumes with CFW markers; never inspect Nintendo game storage, keys or raw NAND.
- Content folders are not evidence of installed games; never infer game versions from mod folders.
- Keep Switch SD read-only: auto-select a card, scan, search and filter; do not add copy/install/removal actions.
- Read existing metadata for compatibility; never clean up old metadata, backups or journals on the card.
- Keep scan cancellation and disconnection guards.
- Test with synthetic card directories and mocked mount discovery; never use real cards as agent verification.

## Data and credentials

- Data lives in `.data/` from source, beside the packaged app, or under `--dir`.
- `settings.json` stores settings; `.catalogs/<catalog>/` stores catalog, download and release records.
- `downloaded/<catalog>/` and `covers/<catalog>/` hold output; `cache/` holds replaceable fetched data.
- Preserve resumable files in `.parts/` and the idempotent migration in `vault/layout.py`.
- Store the SteamGridDB key in the system keyring, with the existing sealed fallback.
  - Settings store only a secret reference; never write the plaintext key to `settings.json` or hash it irreversibly.
  - Keep `.catalogs/secret_key` and keyring account identity stable; moving them can lose saved credentials.

## Configuration, builds and releases

- Configuration precedence: build values, source-only `.env`, then real environment variables.
- Start from `.env.example`; new embedded settings belong in `CONFIG_KEYS`, optional ones in `OPTIONAL_KEYS`.
- `NX_DESK_USER_AGENT` is runtime-only; `NX_DESK_RELEASES_URL` is required for builds.
- Source runs are unversioned; verify self-update with a packaged build.
- Check GitHub self-updates through the public Releases API and download assets over HTTPS; this does not require `gh`.
- Settings manages GitHub PATs; changing/removing a token must wait for active GitHub operations.
- Build naming and update selection share `asset_name()`; renaming assets can strand installed builds.
- Homebrews reads the normalized NX Index feed through optional `NX_DESK_HOMEBREWS_URL`; keep
  source HTML parsing in NX Index. Preserve cached rows on errors and independent List/Grid settings.
- Ports and Homebrews share `ui/list_art.py` and `vault/art_queue.py`. Homebrews images live in
  `covers/_homebrews/`; request only selected/visible entries and keep lookup/key handling shared.
- Build-matrix changes must also update the publish job's `EXPECTED` asset count.
- If editing `assets/icon.svg`, regenerate `icon.ico`, `icon.icns` and `nx_desk/ui/icon.png`.
- Use Conventional Commits: `fix:` and `feat:` trigger releases; `docs:`, `chore:`, `refactor:` and `test:` do not.
- Mark breaking changes with `!` and explain them in the body; avoid the `BREAKING CHANGE:` footer.

## Validation

- Use `unittest` and `unittest.mock`; mock network/GitHub calls and cover changed behavior and failure paths.
- Reuse `tests/helpers.py` fixtures and each area's `case.py`; run tests from the repository root.
- Use `make test` or `python -B -m tests.run [module ...]` so configuration, keyring and external I/O
  are isolated before discovery. Use ordinary fixture filenames, never secret-file names.
- Run `make test` and `make lint` for code changes; tool settings live in their own configuration files.
- Preserve `ui/theme.py` tokens, shared widgets and accessibility in UI changes.
- Describe behavior and validation in reviews; consult the code and README for detailed feature behavior.
