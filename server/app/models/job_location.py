from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.job import Job


class JobLocation(Base):
    __tablename__ = "job_locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(128))
    postal_code: Mapped[str | None] = mapped_column(String(32))

    remote_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    hybrid_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    location_text: Mapped[str | None] = mapped_column(String(512))

    job: Mapped["Job"] = relationship(back_populates="locations")
