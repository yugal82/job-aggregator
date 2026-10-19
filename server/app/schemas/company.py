from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CompanyResponse(BaseModel):
    """A company plus two aggregates: live job count and most-recent sync.

    `active_job_count` counts jobs in status ACTIVE or UPDATED (excludes
    DISCOVERED and CLOSED). `last_synced_at` is MAX(sync_runs.completed_at)
    across every source linked to the company, restricted to successful runs
    — null when no successful sync has ever happened.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    website: str | None
    careers_url: str | None
    logo_url: str | None
    active: bool
    created_at: datetime
    updated_at: datetime

    active_job_count: int = 0
    last_synced_at: datetime | None = None

    # Tier keys the company belongs to, e.g. ["big_tech", "faang"]. Empty when
    # the company isn't listed in any configured tier.
    tiers: list[str] = []


# Alias to keep the client contract readable where a "detail" shape is implied.
CompanyDetail = CompanyResponse
