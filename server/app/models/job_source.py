from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.source import Source


class JobSource(Base):
    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint("source_id", "source_job_id", name="uq_job_sources_source_source_job"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_job_id: Mapped[str] = mapped_column(String(256), nullable=False)

    source_url: Mapped[str | None] = mapped_column(String(1024))
    source_application_url: Mapped[str | None] = mapped_column(String(1024))
    source_title: Mapped[str | None] = mapped_column(String(512))
    source_location: Mapped[str | None] = mapped_column(String(512))
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    job: Mapped["Job"] = relationship(back_populates="sources")
    source: Mapped["Source"] = relationship()
