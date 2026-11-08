from pydantic import BaseModel


# What a card of a grid shows for one row of a model; the model hands it out under ui.cards.layout.CARD_ROLE.
class Card(BaseModel):
    # Names the row in the thumbnails and art caches.
    key: str
    title: str
    subtitle: str
    # A colour token of the theme for the subtitle; "muted" for plain text.
    tone: str = "muted"
    # The icon drawn on a card that has no art.
    icon: str = "gamepad"
    # How far a transfer has come, from 0 to 1; negative while none runs.
    progress: float = -1
