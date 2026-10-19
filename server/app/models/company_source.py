from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SyncPriority
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.source import Source


class CompanySource(Base, TimestampMixin):
    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint("company_id", "source_id", name="uq_company_sources_company_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    adapter: Mapped[str] = mapped_column(String(128), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    priority: Mapped[SyncPriority] = mapped_column(
        SAEnum(
            SyncPriority,
            name="sync_priority",
            native_enum=True,
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=SyncPriority.MEDIUM,
        server_default=SyncPriority.MEDIUM.value,
    )
    last_successful_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempted_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    company: Mapped["Company"] = relationship(back_populates="sources")
    source: Mapped["Source"] = relationship(back_populates="company_links")
