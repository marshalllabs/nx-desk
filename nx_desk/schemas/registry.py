from pydantic import BaseModel, TypeAdapter

from .artwork import StoredSecret
from .catalog import Catalog


# .catalogs/index.json: the catalogs, the active one and the saved settings. Older files may lack
# fields, which then keep these defaults.
class Registry(BaseModel):
    active: str | None = None
    catalogs: list[Catalog] = []
    mod_name: str = ""
    download_dir: str = ""
    upload_source: str = ""
    upload_repo: str = ""
    upload_tag: str = ""
    auto_upload: bool = False
    auto_delete: bool = False
    # The GitHub tab deletes a source folder once its upload is on the release and recorded.
    upload_delete: bool = False
    # Empty in files from before this setting, which then follow the GitHub tab's repository.
    auto_repo: str = ""
    size_units: str = ""
    # Desktop notifications for new mods and finished runs.
    notify: bool = True
    # The interface font; empty or 0 keeps the default.
    font_family: str = ""
    font_size: int = 0
    # Checked by config.clean_compression, so an odd value falls back to the default.
    compression: object = None
    # How the Switch Ports tab shows its entries: "list" or "grid"; anything else means the list.
    ports_view: str = "list"
    homebrews_view: str = "list"
    # How the Catalog tab shows its games: "list" or "grid"; anything else means the list.
    catalog_view: str = "list"
    # Where the SteamGridDB API key is kept; the key itself is never written here.
    art_key: StoredSecret = StoredSecret()


REGISTRY: TypeAdapter[Registry] = TypeAdapter(Registry)
