from pydantic import BaseModel, ConfigDict

from app.models.enums import SourceType


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: SourceType
    provider: str
    base_url: str | None
    active: bool
