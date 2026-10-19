from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum as SAEnum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.enums import SourceType
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.company_source import CompanySource


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    type: Mapped[SourceType] = mapped_column(
        SAEnum(
            SourceType,
            name="source_type",
            native_enum=True,
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    company_links: Mapped[list["CompanySource"]] = relationship(back_populates="source")
