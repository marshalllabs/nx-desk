from pydantic import BaseModel


class Homebrew(BaseModel):
    id: str
    name: str
    description: str = ""
    groups: list[str] = []
    category: str = ""
    version: str = ""
    authors: str = ""
    updated: str = ""
    url: str = ""


class HomebrewSnapshot(BaseModel):
    rows: list[Homebrew]
    version: int
    loading: bool
    error: str
