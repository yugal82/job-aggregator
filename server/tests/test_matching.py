"""Unit tests for the deterministic facet logic (no DB)."""
from decimal import Decimal
from types import SimpleNamespace

from app.matching import facet_counts, match_score
from app.matching.explain import build_explanation
from app.matching.facets import (
    experience_facet,
    location_facet,
    role_facet,
    salary_facet,
    skills_facet,
    visa_facet,
)
from app.matching.profile import has_match_signal
from app.models.user_profile import UserProfile


def _profile(**overrides) -> UserProfile:
    defaults = dict(
        user_id=1,
        target_roles=[],
        target_locations=[],
        skills=[],
        years_experience=None,
        requires_sponsorship=False,
        resume_text=None,
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def _loc(text: str) -> SimpleNamespace:
    return SimpleNamespace(location_text=text)


def _job(**overrides) -> SimpleNamespace:
    defaults = dict(
        canonical_title="Backend Engineer",
        description=None,
        salary_min=None,
        salary_max=None,
        salary_currency=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestRoleFacet:
    def test_strong_when_target_appears_in_title(self):
        p = _profile(target_roles=["backend", "fullstack"])
        f = role_facet(p, "Senior Backend Engineer")
        assert f.bucket == "strong"
        assert f.detail == {"matched_target": "backend"}

    def test_gap_when_no_target_matches(self):
        p = _profile(target_roles=["backend"])
        f = role_facet(p, "Product Designer")
        assert f.bucket == "gap"

    def test_neutral_without_targets(self):
        f = role_facet(_profile(), "Anything")
        assert f.bucket == "neutral"


class TestLocationFacet:
    def test_strong_when_a_location_matches(self):
        p = _profile(target_locations=["San Francisco", "Remote"])
        f = location_facet(p, [_loc("San Francisco, CA"), _loc("New York")])
        assert f.bucket == "strong"
        assert f.detail["matched_locations"] == ["San Francisco, CA"]

    def test_gap_when_nothing_matches(self):
        p = _profile(target_locations=["San Francisco"])
        f = location_facet(p, [_loc("London"), _loc("Dublin")])
        assert f.bucket == "gap"

    def test_neutral_without_targets(self):
        f = location_facet(_profile(), [_loc("Anywhere")])
        assert f.bucket == "neutral"


class TestSkillsFacet:
    def test_strong_above_threshold(self):
        p = _profile(skills=["python", "postgres", "docker", "react", "aws"])
        f = skills_facet(p, "Backend Engineer", "We use Python, Postgres, Docker, and AWS.")
        assert f.bucket == "strong"
        assert set(f.detail["matched"]) >= {"python", "postgres", "docker", "aws"}

    def test_gap_when_none_match(self):
        p = _profile(skills=["python", "postgres"])
        f = skills_facet(p, "Marketing Lead", "Grow the brand.")
        assert f.bucket == "gap"
        assert f.detail["matched"] == []

    def test_neutral_partial(self):
        p = _profile(skills=["python", "postgres", "docker", "k8s", "aws"])
        f = skills_facet(p, "Engineer", "Python only.")
        assert f.bucket == "neutral"
        assert f.detail["matched"] == ["python"]


class TestExperienceFacet:
    def test_strong_when_profile_meets_requirement(self):
        p = _profile(years_experience=5)
        f = experience_facet(p, "We need 3+ years of experience.")
        assert f.bucket == "strong"
        assert f.detail["required_min"] == 3

    def test_gap_when_profile_short(self):
        p = _profile(years_experience=1)
        f = experience_facet(p, "At least 3 years of experience required.")
        assert f.bucket == "gap"
        assert f.detail == {"required_min": 3, "required_max": None, "profile": 1}

    def test_neutral_when_description_lacks_signal(self):
        p = _profile(years_experience=2)
        f = experience_facet(p, "Great team, free snacks.")
        assert f.bucket == "neutral"

    def test_parses_range(self):
        p = _profile(years_experience=3)
        f = experience_facet(p, "3-5 years of experience")
        assert f.detail == {"required_min": 3, "required_max": 5, "profile": 3}


class TestSalaryFacet:
    def test_strong_when_disclosed(self):
        f = salary_facet(_job(salary_min=Decimal("100000"), salary_max=Decimal("150000")))
        assert f.bucket == "strong"
        assert f.detail["salary_max"] == 150000.0

    def test_neutral_when_not_disclosed(self):
        f = salary_facet(_job(salary_max=None))
        assert f.bucket == "neutral"


class TestVisaFacet:
    def test_neutral_when_profile_does_not_need(self):
        f = visa_facet(_profile(requires_sponsorship=False), "No sponsorship")
        assert f.bucket == "neutral"

    def test_gap_when_description_says_no(self):
        p = _profile(requires_sponsorship=True)
        f = visa_facet(p, "We do not sponsor visas for this role.")
        assert f.bucket == "gap"

    def test_strong_when_description_says_yes(self):
        p = _profile(requires_sponsorship=True)
        f = visa_facet(p, "We will sponsor visa applications.")
        assert f.bucket == "strong"

    def test_neutral_when_unmentioned(self):
        p = _profile(requires_sponsorship=True)
        f = visa_facet(p, "Great team, snacks.")
        assert f.bucket == "neutral"
        assert f.detail == {
            "profile_needs_sponsorship": True,
            "job_offers_sponsorship": None,
        }


class TestExplanationAndScore:
    def test_counts_and_score_ranking(self):
        p = _profile(
            target_roles=["backend"],
            target_locations=["San Francisco"],
            skills=["python", "postgres"],
            years_experience=5,
        )
        good = build_explanation(
            p,
            _job(
                canonical_title="Backend Engineer",
                description="Python and Postgres required. 3+ years of experience.",
                salary_max=Decimal("200000"),
            ),
            [_loc("San Francisco, CA")],
        )
        bad = build_explanation(
            p,
            _job(
                canonical_title="Product Manager",
                description="Lead a team. 8+ years of experience.",
            ),
            [_loc("Berlin")],
        )
        assert match_score(good) > match_score(bad)
        strong_good, gap_good = facet_counts(good)
        strong_bad, gap_bad = facet_counts(bad)
        assert strong_good > strong_bad
        assert gap_bad > gap_good


class TestHasMatchSignal:
    def test_profile_with_target_roles_has_signal(self):
        assert has_match_signal(_profile(target_roles=["backend"])) is True

    def test_empty_profile_has_no_signal(self):
        assert has_match_signal(_profile()) is False

    def test_none_profile_has_no_signal(self):
        assert has_match_signal(None) is False
