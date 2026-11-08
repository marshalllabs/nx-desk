from typing import Literal, Protocol

from pydantic import BaseModel, TypeAdapter


# What artwork needs from catalog mods, ports and homebrews.
class ArtSubject(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...


# Where a saved secret lives: the system keyring, sealed in the registry, or nowhere.
SecretPlace = Literal["", "keyring", "sealed"]


# What the registry keeps for a secret; never the secret itself.
class StoredSecret(BaseModel):
    place: SecretPlace = ""
    # Only for "sealed": the text sealed with the key in .catalogs/secret_key.
    sealed: str = ""


# What SteamGridDB has for one game name; empty URLs mean the catalog's art is used.
class ArtLookup(BaseModel):
    game_id: int = 0
    cover: str = ""
    background: str = ""
    checked_at: float = 0
    # The matching rules it was made under (config.ART_LOOKUP_RULES); 0 for lookups saved before there were any.
    rules: int = 0


ART_LOOKUPS: TypeAdapter[dict[str, ArtLookup]] = TypeAdapter(dict[str, ArtLookup])
