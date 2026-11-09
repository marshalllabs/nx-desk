from typing import List

from pydantic import BaseModel


class Homebrew(BaseModel):
    id: str
    name: str
    description: str = ""
    groups: List[str] = []
    category: str = ""
    version: str = ""
    authors: str = ""
    updated: str = ""
    url: str = ""


class HomebrewSnapshot(BaseModel):
    rows: List[Homebrew]
    version: int
    loading: bool
    error: str
