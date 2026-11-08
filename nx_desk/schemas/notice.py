from pydantic import BaseModel


# A desktop notification that the vault queues and the window shows.
class Notice(BaseModel):
    title: str
    text: str
