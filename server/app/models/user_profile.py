from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class UserProfile(Base, TimestampMixin):
    """One row per user; the matcher reads from this to produce facet
    explanations. Phase-6-client scope keeps every field optional so a bare
    profile (no targets, no skills) just produces neutral facets."""

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )

    target_roles: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    target_locations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    skills: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )

    years_experience: Mapped[int | None] = mapped_column(Integer)
    requires_sponsorship: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Reserved for Phase 9's semantic matching — not used by the deterministic
    # facet logic that ships here.
    resume_text: Mapped[str | None] = mapped_column(Text)
