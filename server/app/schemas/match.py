"""Match-explanation shapes exposed to the client.

Follows the Phase-6-client contract: one `facets` array, no numeric score in
the response. The server computes a score internally for ranking only.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

FacetBucket = Literal["strong", "gap", "neutral"]


class MatchFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    bucket: FacetBucket
    label: str
    detail: dict[str, Any] | None = None


class MatchExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facets: list[MatchFacet]
