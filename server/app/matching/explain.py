"""Compose per-facet computers into a MatchExplanation + an internal score.

The internal score is only used for server-side ranking (sort=match,
/recommendations). It never crosses the API boundary.
"""
from collections.abc import Iterable
from uuid import UUID

from app.matching.facets import (
    experience_facet,
    location_facet,
    role_facet,
    salary_facet,
    skills_facet,
    visa_facet,
)
from app.models.job import Job
from app.models.job_location import JobLocation
from app.models.user_profile import UserProfile
from app.schemas.match import MatchExplanation

# Weight each facet's contribution to the server-internal ranking score.
# A "strong" facet adds its weight; a "gap" subtracts half its weight.
# Neutrals never contribute — they're informational only.
_WEIGHTS: dict[str, float] = {
    "role": 3.0,
    "skills": 2.0,
    "location": 2.0,
    "experience_years": 1.5,
    "salary": 0.5,
    "visa": 1.0,
}


def build_explanation(
    profile: UserProfile,
    job: Job,
    locations: Iterable[JobLocation] = (),
) -> MatchExplanation:
    facets = [
        role_facet(profile, job.canonical_title),
        location_facet(profile, locations),
        skills_facet(profile, job.canonical_title, job.description),
        experience_facet(profile, job.description),
        salary_facet(job),
        visa_facet(profile, job.description),
    ]
    return MatchExplanation(facets=facets)


def match_score(explanation: MatchExplanation) -> float:
    score = 0.0
    for facet in explanation.facets:
        w = _WEIGHTS.get(facet.key, 1.0)
        if facet.bucket == "strong":
            score += w
        elif facet.bucket == "gap":
            score -= w * 0.5
    return score


def facet_counts(explanation: MatchExplanation) -> tuple[int, int]:
    strong = sum(1 for f in explanation.facets if f.bucket == "strong")
    gap = sum(1 for f in explanation.facets if f.bucket == "gap")
    return strong, gap


def compute_matches_for_jobs(
    profile: UserProfile,
    jobs: Iterable[Job],
    locations_by_job: dict[UUID, list[JobLocation]],
) -> dict[UUID, MatchExplanation]:
    """Vectorized convenience: build an explanation per job in one pass."""
    out: dict[UUID, MatchExplanation] = {}
    for job in jobs:
        out[job.id] = build_explanation(
            profile, job, locations_by_job.get(job.id, [])
        )
    return out
