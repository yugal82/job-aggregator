"""Wire-format models for adapters.

RawJob:      what an adapter emits from `discover()`/`get_job()`. Adapters may
             pre-parse convenient fields for the caller, but the full source
             payload is always in `payload`.

CanonicalJob: the normalized shape produced by `normalize()`, mirroring §9 of
             the design doc. This is what the ingestion pipeline consumes.
"""
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RawJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_job_id: str
    source_url: str | None = None
    application_url: str | None = None
    title: str
    location_text: str | None = None
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    payload: dict[str, Any]


class CanonicalLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    remote_allowed: bool = False
    hybrid_allowed: bool = False
    location_text: str | None = None


class CanonicalJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_slug: str
    source_provider: str
    source_job_id: str

    title: str
    description: str | None = None
    locations: list[CanonicalLocation] = Field(default_factory=list)

    employment_type: str | None = None
    workplace_type: str | None = None

    department: str | None = None
    team: str | None = None

    # Source-native career-level token (e.g. "IC2", "L3", "SDE II"). None
    # when the adapter doesn't surface one. Case preserved for display;
    # filtering is case-insensitive at the SQL layer.
    level: str | None = None

    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str | None = None

    posted_at: datetime | None = None
    updated_at: datetime | None = None

    application_url: str | None = None
    source_url: str | None = None

    requisition_id: str | None = None

    raw_data: dict[str, Any]
    content_hash: str
