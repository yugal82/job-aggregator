"""Deterministic per-facet computers. Each returns a MatchFacet given a
UserProfile and the relevant job attributes. No LLM in the loop.

Facets:
  role              — target role keywords matched against canonical_title
  location          — target locations matched against job_locations
  skills            — profile skills matched against title + description text
  experience_years  — regex "N+ years" / "N-M years" vs profile years
  salary            — strong iff salary_max is disclosed on the job
  visa              — regex over description, scoped to users who need sponsorship
"""
import re
from typing import Iterable

from app.models.job import Job
from app.models.job_location import JobLocation
from app.models.user_profile import UserProfile
from app.schemas.match import MatchFacet

_YEARS_RANGE = re.compile(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(?:\+\s*)?years", re.IGNORECASE)
_YEARS_MIN = re.compile(
    r"(\d+)\+?\s*years?\s*(?:of\s+)?(?:professional\s+|relevant\s+)?experience",
    re.IGNORECASE,
)
_YEARS_AT_LEAST = re.compile(r"at least\s*(\d+)\s*years?", re.IGNORECASE)

_VISA_YES = re.compile(
    r"(we sponsor|visa sponsorship (?:is )?available|will sponsor|sponsors? h.?1b|"
    r"we offer visa|offer sponsorship)",
    re.IGNORECASE,
)
_VISA_NO = re.compile(
    r"(no sponsorship|not sponsor|unable to sponsor|without sponsorship|"
    r"not provide sponsorship|do not sponsor|cannot sponsor)",
    re.IGNORECASE,
)


def role_facet(profile: UserProfile, title: str | None) -> MatchFacet:
    if not profile.target_roles:
        return MatchFacet(
            key="role", bucket="neutral", label="No target roles configured"
        )
    text = (title or "").lower()
    for target in profile.target_roles:
        if target.lower() in text:
            return MatchFacet(
                key="role",
                bucket="strong",
                label=f"{title} matches your target roles",
                detail={"matched_target": target},
            )
    return MatchFacet(
        key="role",
        bucket="gap",
        label="Role doesn't match your targets",
    )


def location_facet(
    profile: UserProfile, locations: Iterable[JobLocation]
) -> MatchFacet:
    if not profile.target_locations:
        return MatchFacet(
            key="location", bucket="neutral", label="No target locations configured"
        )
    matched: list[str] = []
    for target in profile.target_locations:
        target_lower = target.lower()
        for loc in locations:
            text = (loc.location_text or "").lower()
            if target_lower in text:
                matched.append(loc.location_text)
                break
    matched_unique = list(dict.fromkeys(matched))  # preserves order, dedups
    if matched_unique:
        preview = ", ".join(matched_unique[:3])
        return MatchFacet(
            key="location",
            bucket="strong",
            label=f"Available in: {preview}",
            detail={"matched_locations": matched_unique},
        )
    return MatchFacet(
        key="location",
        bucket="gap",
        label="Not in your target locations",
    )


def skills_facet(
    profile: UserProfile, title: str | None, description: str | None
) -> MatchFacet:
    if not profile.skills:
        return MatchFacet(
            key="skills", bucket="neutral", label="No skills configured"
        )

    corpus = ((title or "") + " " + (description or "")).lower()
    matched: list[str] = []
    missing: list[str] = []
    for skill in profile.skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, corpus):
            matched.append(skill)
        else:
            missing.append(skill)

    threshold = max(2, int(len(profile.skills) * 0.4))

    if len(matched) >= threshold:
        preview = ", ".join(matched[:4])
        return MatchFacet(
            key="skills",
            bucket="strong",
            label=f"Matches: {preview}",
            detail={"matched": matched, "missing": missing},
        )
    if not matched and len(profile.skills) >= 2:
        preview = ", ".join(missing[:4])
        return MatchFacet(
            key="skills",
            bucket="gap",
            label=f"Missing: {preview}",
            detail={"matched": matched, "missing": missing},
        )
    return MatchFacet(
        key="skills",
        bucket="neutral",
        label=f"Partial skill match ({len(matched)}/{len(profile.skills)})",
        detail={"matched": matched, "missing": missing},
    )


def experience_facet(profile: UserProfile, description: str | None) -> MatchFacet:
    if profile.years_experience is None:
        return MatchFacet(
            key="experience_years",
            bucket="neutral",
            label="Experience target not set",
        )
    if not description:
        return MatchFacet(
            key="experience_years",
            bucket="neutral",
            label="Experience requirement not mentioned",
        )

    required_min: int | None = None
    required_max: int | None = None

    m = _YEARS_RANGE.search(description)
    if m:
        required_min = int(m.group(1))
        required_max = int(m.group(2))
    else:
        m = _YEARS_MIN.search(description) or _YEARS_AT_LEAST.search(description)
        if m:
            required_min = int(m.group(1))

    if required_min is None:
        return MatchFacet(
            key="experience_years",
            bucket="neutral",
            label="Experience requirement not mentioned",
        )

    detail = {
        "required_min": required_min,
        "required_max": required_max,
        "profile": profile.years_experience,
    }
    if profile.years_experience >= required_min:
        return MatchFacet(
            key="experience_years",
            bucket="strong",
            label=f"You meet the {required_min}+ year requirement",
            detail=detail,
        )
    return MatchFacet(
        key="experience_years",
        bucket="gap",
        label=f"{required_min}+ years requested",
        detail=detail,
    )


def salary_facet(job: Job) -> MatchFacet:
    if job.salary_max is not None:
        return MatchFacet(
            key="salary",
            bucket="strong",
            label=f"Salary disclosed: up to ${float(job.salary_max):,.0f}",
            detail={
                "salary_min": float(job.salary_min) if job.salary_min is not None else None,
                "salary_max": float(job.salary_max),
                "salary_currency": job.salary_currency,
            },
        )
    return MatchFacet(key="salary", bucket="neutral", label="Salary not disclosed")


def visa_facet(profile: UserProfile, description: str | None) -> MatchFacet:
    if not profile.requires_sponsorship:
        return MatchFacet(
            key="visa",
            bucket="neutral",
            label="Visa sponsorship not required",
            detail={"profile_needs_sponsorship": False, "job_offers_sponsorship": None},
        )

    if not description:
        return MatchFacet(
            key="visa",
            bucket="neutral",
            label="Visa sponsorship not mentioned",
            detail={"profile_needs_sponsorship": True, "job_offers_sponsorship": None},
        )

    # Check negative first — "we do not sponsor" would also partial-match the
    # positive pattern on "sponsor".
    if _VISA_NO.search(description):
        return MatchFacet(
            key="visa",
            bucket="gap",
            label="This role does not offer sponsorship",
            detail={"profile_needs_sponsorship": True, "job_offers_sponsorship": False},
        )
    if _VISA_YES.search(description):
        return MatchFacet(
            key="visa",
            bucket="strong",
            label="This role offers visa sponsorship",
            detail={"profile_needs_sponsorship": True, "job_offers_sponsorship": True},
        )
    return MatchFacet(
        key="visa",
        bucket="neutral",
        label="Visa sponsorship not mentioned",
        detail={"profile_needs_sponsorship": True, "job_offers_sponsorship": None},
    )
