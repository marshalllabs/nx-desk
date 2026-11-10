# Release state contract

- Both applications use the same version 1 schema in `schemas/release_state.py` and rules in `utils/release_state.py`.
- Keep these modules and `tests/fixtures/release_state_contract.json` identical across both repositories.
- Run both test suites after changing the contract; each application remains independently installable.

| Field | Meaning |
| --- | --- |
| `version` | Document format version, currently `1` |
| `catalog` | Catalog URL; Gist revision hashes are removed from raw URLs |
| `mods.<id>.sha256` | Lowercase SHA-256 of the original source download, never the repacked asset |
| `mods.<id>.version` | Mod version from the catalog |
| `mods.<id>.game_version` | Original game-version text from the catalog |
| `mods.<id>.folder` | Actual folder packaged in the uploaded ZIP |
| `mods.<id>.files` | Sorted, unique asset names, including every split part |
| `mods.<id>.uploaded_at` | UTC upload timestamp; metadata repair preserves it |

## Reading and comparison

- Missing or null legacy text fields become empty strings; missing or null file lists become empty lists.
- Missing game-version text can be displayed from the final `[version]` in the stored folder name.
- Invalid JSON, malformed record maps and unsupported format versions stop state-dependent writes.
- When both original checksums exist, checksum equality decides whether the content matches.
   - Different names, mod-version text or game-version text do not force transfers when the checksum matches.
- Otherwise compare non-empty mod versions; also compare game versions when both are known.
   - Game-version fallback extracts the first numeric version and ignores a leading `v` and descriptive text.
   - An unknown legacy game version does not force a transfer when mod versions match.
   - Without a checksum pair or a usable mod-version pair, content identity is unknown.
- Recorded assets must exist, including all split parts; match asset names without case sensitivity.
- Another mod ID may reuse an existing record only when its original checksum matches.
- Missing assets or changed content require a transfer; metadata and folder-name differences alone do not.

## Writing

- Both automatic and manual uploads write every record field, including `game_version`.
- Record only a successful upload; never advance a failed mod's checksum, version or upload timestamp.
- A matching checksum permits catalog metadata repair without downloading or uploading the mod.
   - Preserve the actual folder, asset references, upload timestamp and unknown record fields.
   - Resolve file references to the actual spelling of existing assets.
   - Do not invent a missing original checksum from a version-only match.
- Record every catalog ID that shares an uploaded original file.
- Read the release state again before replacement and merge only the changed records.
- Upload and verify a temporary state asset before replacing the published state.
- Use one writer per release; this contract does not provide a distributed lock between applications.
