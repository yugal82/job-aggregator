from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Computed,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import JobStatus
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.job_location import JobLocation
    from app.models.job_source import JobSource
    from app.models.job_version import JobVersion


_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('english', coalesce(canonical_title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_search_vector", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )

    canonical_title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    employment_type: Mapped[str | None] = mapped_column(String(64))
    workplace_type: Mapped[str | None] = mapped_column(String(64))

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))

    department: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(128))

    # Source-native career-level token (e.g. Microsoft "IC2", Google "L3",
    # Amazon "SDE II"). Nullable because most adapters don't populate it.
    level: Mapped[str | None] = mapped_column(String(32))

    application_url: Mapped[str | None] = mapped_column(String(1024))
    canonical_url: Mapped[str | None] = mapped_column(String(1024))

    content_hash: Mapped[str | None] = mapped_column(String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    requisition_id: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(
            JobStatus,
            name="job_status",
            native_enum=True,
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=JobStatus.DISCOVERED,
        server_default=JobStatus.DISCOVERED.value,
        index=True,
    )
    consecutive_missed_syncs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Postgres-generated full-text search index. Phase 10 queries use
    # `search_vector @@ websearch_to_tsquery('english', :q)`.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(_SEARCH_VECTOR_EXPR, persisted=True),
        nullable=True,
    )

    company: Mapped["Company"] = relationship(back_populates="jobs")
    locations: Mapped[list["JobLocation"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    sources: Mapped[list["JobSource"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    versions: Mapped[list["JobVersion"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobVersion.version",
    )
