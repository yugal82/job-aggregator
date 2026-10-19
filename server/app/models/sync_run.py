from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import SyncRunStatus


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_source_id: Mapped[int] = mapped_column(
        ForeignKey("company_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    adapter: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[SyncRunStatus] = mapped_column(
        SAEnum(
            SyncRunStatus,
            name="sync_run_status",
            native_enum=True,
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    jobs_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    jobs_closed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    error: Mapped[str | None] = mapped_column(Text)
