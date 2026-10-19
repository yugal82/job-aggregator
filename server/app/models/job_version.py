from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.job import Job


class JobVersion(Base):
    """Immutable snapshot of a job's content whenever its canonical content hash
    changes. Rows are append-only — never updated after insert.
    """

    __tablename__ = "job_versions"
    __table_args__ = (
        UniqueConstraint("job_id", "version", name="uq_job_versions_job_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    employment_type: Mapped[str | None] = mapped_column(String(64))
    workplace_type: Mapped[str | None] = mapped_column(String(64))

    department: Mapped[str | None] = mapped_column(String(128))
    team: Mapped[str | None] = mapped_column(String(128))

    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_currency: Mapped[str | None] = mapped_column(String(8))

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped["Job"] = relationship(back_populates="versions")
