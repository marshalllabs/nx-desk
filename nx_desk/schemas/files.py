from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class FileMove(BaseModel):
    source: Path
    target: Path


class LegacyCatalogFile(BaseModel):
    folder: str
    name: Optional[str]
