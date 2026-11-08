from pydantic import BaseModel


# One entry of the Switch Ports list, after catalog.ports.parse_ports.
class Port(BaseModel):
    id: str
    name: str
    platform: str
    # "port" or "emulator".
    kind: str = "port"
    # The system an emulator runs; empty for ports.
    emulates: str = ""
    version: str = ""
    updated: str = ""
    # Only HTTPS links are kept.
    url: str = ""
    host: str = ""
    thread: str = ""
    status: str = ""


class PortSnapshot(BaseModel):
    rows: list[Port]
    version: int
    loading: bool
    error: str
