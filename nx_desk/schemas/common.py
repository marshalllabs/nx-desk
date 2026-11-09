from typing import Callable

from pydantic import BaseModel


class LogEntry(BaseModel):
    level: str
    time: str
    game: str
    text: str


# Callbacks may accept positional-only arguments.
Progress = Callable[[int], None]
Report = Callable[[str], None]
