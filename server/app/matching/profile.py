from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile


async def load_profile(session: AsyncSession, user_id: int) -> UserProfile | None:
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


def has_match_signal(profile: UserProfile | None) -> bool:
    """Return True iff the profile has enough info to drive at least one
    non-neutral facet. An all-empty profile makes every facet neutral, so the
    caller treats it as "no signal" and skips match computation."""
    if profile is None:
        return False
    return bool(
        profile.target_roles
        or profile.target_locations
        or profile.skills
        or profile.years_experience is not None
        or profile.requires_sponsorship
    )
