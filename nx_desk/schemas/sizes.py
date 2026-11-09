from pydantic import BaseModel, ConfigDict


class SizeScale(BaseModel):
    model_config = ConfigDict(frozen=True)

    base: int
    kilo: str
    mega: str
    giga: str
