from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.enums import JobStatus
from app.schemas.company import CompanyResponse
from app.schemas.match import MatchExplanation
from app.schemas.source import SourceResponse


class JobLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str | None
    state: str | None
    country: str | None
    postal_code: str | None
    remote_allowed: bool
    hybrid_allowed: bool
    location_text: str | None


class JobSummary(BaseModel):
    """Compact job representation returned in list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: int
    canonical_title: str
    employment_type: str | None
    workplace_type: str | None
    department: str | None
    team: str | None
    level: str | None = None
    posted_at: datetime | None
    first_seen_at: datetime
    application_url: str | None
    canonical_url: str | None
    status: JobStatus

    # Lightweight match preview; null when no profile signal is available.
    # Full facets live on JobDetail / RecommendedJob to keep list payloads small.
    match_strong_count: int | None = None
    match_gap_count: int | None = None


class JobSourceLink(BaseModel):
    """A `job_sources` row with its parent source joined in."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_url: str | None
    source_application_url: str | None
    source_title: str | None
    source_location: str | None
    source_posted_at: datetime | None
    is_active: bool
    source: SourceResponse


class JobDetail(JobSummary):
    """Full job representation returned by the detail endpoint."""

    description: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    salary_currency: str | None
    last_seen_at: datetime
    closed_at: datetime | None
    content_hash: str | None
    requisition_id: str | None
    company: CompanyResponse | None = None
    locations: list[JobLocationResponse] = []
    sources: list[JobSourceLink] = []
    match: MatchExplanation | None = None


class RecommendedJob(JobSummary):
    """A job that /api/recommendations returns, with its full match attached."""

    match: MatchExplanation
