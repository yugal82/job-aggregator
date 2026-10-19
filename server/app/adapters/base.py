from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.adapters.http import HTTPClient
from app.adapters.models import CanonicalJob, RawJob


class JobSourceAdapter(ABC):
    """Contract implemented by every source adapter.

    Adapters own only the source-specific fetch + parse logic. Persistence,
    deduplication, and classification live outside the adapter.
    """

    #: registry key — subclasses must set this
    provider: ClassVar[str]

    def __init__(
        self,
        *,
        http: HTTPClient,
        config: dict[str, Any],
        company_slug: str,
    ) -> None:
        self.http = http
        self.config = config
        self.company_slug = company_slug

    @abstractmethod
    async def discover(self) -> list[RawJob]:
        """Return every currently listed job on the source."""

    @abstractmethod
    async def get_job(self, source_job_id: str) -> RawJob:
        """Fetch a single job by its source-native id."""

    @abstractmethod
    def normalize(self, raw: RawJob) -> CanonicalJob:
        """Transform a raw record into the canonical shape."""
