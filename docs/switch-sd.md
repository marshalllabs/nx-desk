# Switch SD

## Detection and scanning

- Check mounted FAT32/exFAT volumes every three seconds; never enumerate raw disks or require administrator access.
- Require `atmosphere/package3`, or an Atmosphere contents directory with Hekate/emuMMC configuration markers.
- Ignore ordinary cards, unsupported filesystems and symlinked markers; expose read-only cards.
- Detection identifies a CFW filesystem layout, not physical card authenticity; a mounted clone can look identical.
- Select the first detected card automatically; retain the selected card while available.
- Rescan identity changes; when a card disappears, select the first remaining card or clear the content list.
- Initial selection and **Scan card** scan `atmosphere/contents/<title-id>`; ordinary polling does not rehash unchanged cards.
- Match names and categories through all Title IDs groups (`games`, `system`, `sysmodules`), with active-catalog fallback.
- Refresh displayed names/categories after Title IDs changes without re-reading or rehashing card content.
- Recognize RomFS, ExeFS, cheats, `romfs.bin` and `exefs.nsp` as filesystem content types.
- Category comes from Title IDs data; do not guess system/sysmodule classification from ID prefixes.
- Card content defaults to Game, or All when no Game content exists; names sort in ascending order.
- Category uses the shared checkbox popup from Ports/Homebrews; Clear shows all categories.
- Preserve manually chosen categories until the selected card changes; search does not change the default category.
- The final Action column provides a compact copy icon with a tooltip and a brief success checkmark.
- Ctrl+C copies selected visible Title IDs in table order, one per line.
- Category filtering and search apply to card content. Background polling preserves input focus.
- Never inspect installed Nintendo content, raw NAND, encryption keys or sysMMC/emuMMC game databases.
- A content folder does not prove game installation or runtime mod activation.

| Metadata status | Version behavior |
| --- | --- |
| Empty | Unmanaged content; unknown names, categories and versions stay blank |
| Verified copy | Exact file set and SHA-256 values match NX Desk metadata |
| Mixed / modified | Extra, missing or changed files; versions remain unknown |
| Invalid metadata | Metadata cannot be validated; versions remain unknown |
| Unreadable / unsafe | Unsafe paths, symlinks or filesystem errors prevent scanning |

- `Mod version` and `Target game` describe the copied download record, not the console's installed game version.
- Read existing per-title `.nx-desk.json` metadata for compatibility; never create or update it.

## Read-only scope

- Mod copying, installation, removal, archive discovery and backup creation are not available.
- Never write, extract, rename or delete files on the selected card.
- Existing `atmosphere/.nx-desk-copy-*/` directories may contain recovery data from older copies.
  Scanning reports their presence but never changes or deletes them.
- Installed games, update/DLC inventories and compatibility checks require a later console inventory feature.
- Network/USB companion protocols and enable/disable management remain outside this phase.
