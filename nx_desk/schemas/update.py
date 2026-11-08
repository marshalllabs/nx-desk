from pydantic import BaseModel, ConfigDict


class AppAsset(BaseModel):
    url: str
    size: int
    sha256: str


class AppUpdate(BaseModel):
    tag: str
    url: str
    asset: AppAsset | None


# The self-update download, while it runs; empty fields until it starts.
class UpdateJob(BaseModel):
    # Updated field by field while it runs, so each change is checked too.
    model_config = ConfigDict(validate_assignment=True)

    phase: str = ""
    done: int = 0
    total: int = 0
    message: str = ""
