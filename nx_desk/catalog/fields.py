from ..schemas.catalog import Highlight
from ..schemas.examples import CatalogExample, ExampleMod

# The canonical fields NXDesk works with, and the source keys we recognise for each
# without being told. Catalogs from different projects name the same thing differently
# (English, Vietnamese, nested under a files array), so we try each alias in turn. A field
# mapping supplied per catalog overrides this. Dotted aliases dig into nested dicts/lists,
# e.g. "files.0.url" reads the first file's url. The first alias of each field is the key
# NXDesk's own catalogs use, so a catalog with no surprises parses exactly as before.
FIELD_ALIASES = {
    "id": ["id", "slug", "key", "ma", "ma_game", "game_id"],
    "name": ["name", "title", "ten_game", "ten", "game_name"],
    "title_id": ["title_id", "titleid", "tid", "title_id_game", "ma_tua"],
    "version": ["mod_version", "version", "phien_ban", "ver", "mod_ver"],
    "game_version": ["game_version", "phien_ban_game", "phien_ban_yeu_cau", "game_ver"],
    "sha256": [
        "sha256",
        "sha",
        "hash",
        "checksum",
        "sha_256",
        "files.0.sha256",
        "tap_tin.0.sha256",
        "file.sha256",
    ],
    "size": [
        "size",
        "dung_luong",
        "dung_luong_tap_tin",
        "filesize",
        "file_size",
        "bytes",
        "files.0.size",
        "tap_tin.0.dung_luong",
        "file.size",
    ],
    "url": [
        "url",
        "download",
        "download_url",
        "link",
        "tai_ve",
        "duong_dan",
        "files.0.url",
        "tap_tin.0.tai_ve",
        "tap_tin.0.url",
        "file.url",
    ],
    "mirrors": ["mirrors", "mirror", "links", "guong"],
    "cover": ["cover", "cover_url", "image", "thumbnail", "anh", "anh_bia", "poster"],
    "background": ["background", "banner", "anh_nen", "bg"],
    "tagline": ["tagline", "slogan", "mo_ta_ngan"],
    "developer": ["developer", "dev", "nha_phat_trien", "studio"],
    "release": ["release", "release_date", "ngay_phat_hanh"],
    "translator": ["translator", "nguoi_dich", "dich_gia", "nhom_dich"],
    "tags": ["tags", "genres", "the_loai", "ten_the_loai", "categories", "danh_muc"],
    "description": ["description", "desc", "mo_ta"],
    "highlights": ["highlights", "diem_noi_bat"],
    "done": ["done", "da_lam"],
    "kept": ["kept", "giu_lai"],
    "changelog": ["changelog", "lich_su", "ghi_chu"],
    "credit": ["credit", "credits", "cam_on"],
}

# Keys whose value is the array of games. Checked in order; a top-level JSON array is used
# as-is. "__root__" in a mapping overrides this.
ROOT_ALIASES = [
    "mods",
    "games",
    "items",
    "data",
    "list",
    "catalog",
    "patches",
    "danh_sach",
]

# A catalog every field of which is found without a mapping, shown in the catalog dialog.
CATALOG_TEMPLATE = CatalogExample(
    mods=[
        ExampleMod(
            id="example-game",
            title_id="0100000000010000",
            name="Example Game",
            game_version="1.0.0",
            mod_version="v1",
            sha256="<SHA-256 of the zip, 64 hex characters>",
            size=12345678,
            url="https://example.com/example-game.zip",
            mirrors=["https://mirror.example.com/example-game.zip", "gdrive:<Google Drive file id>"],
            tagline="One line about the game",
            developer="Studio",
            release="2024-01-31",
            translator="Team",
            tags=["Action", "Adventure"],
            description=["First paragraph.", "Second paragraph."],
            highlights=[Highlight(title="For game version", text="1.0.0")],
            done=["What the mod changes"],
            kept=["What it leaves as it was"],
            changelog="What changed in this version",
            credit="Thanks to everyone who helped",
            cover="https://example.com/cover.jpg",
            background="https://example.com/background.jpg",
        ),
    ],
)

# Fields the "advanced" panel of the catalog dialog lets the user map by hand.
MAPPABLE_FIELDS = [
    ("__root__", "Games array (root)"),
    ("id", "ID"),
    ("name", "Game name"),
    ("title_id", "Title ID"),
    ("version", "Mod version"),
    ("game_version", "Game version"),
    ("url", "Download URL"),
    ("sha256", "SHA-256"),
    ("size", "Size"),
    ("cover", "Cover"),
]
