from pydantic import BaseModel


class TitleRow(BaseModel):
    id: str
    name: str
    section: str
    detail: str


class TitleSnapshot(BaseModel):
    rows: list[TitleRow]
    version: int
    loading: bool
    error: str
