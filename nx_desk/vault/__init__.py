from pathlib import Path
from typing import Union

from .app_update import AppUpdates
from .artwork import Artwork
from .catalogs import Catalogs
from .compare import Comparing
from .download_queue import DownloadQueue
from .homebrews import Homebrews
from .options import Options
from .ports import Ports
from .retry import Retrying
from .switch_sd import SwitchSD
from .titles import Titles


# All state and logic. Each mixin covers one area, in the file named after it.
class Vault(
    DownloadQueue,
    Retrying,
    Comparing,
    Catalogs,
    Options,
    AppUpdates,
    Homebrews,
    Titles,
    Ports,
    Artwork,
    SwitchSD,
):
    def __init__(self, base: Union[Path, str]) -> None:
        super().__init__(base=base)
        self._prune_logs()
