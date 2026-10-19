"""Cross-source content fingerprint for dedup Level 4.

Unlike the per-source ``content_hash`` the adapter emits (which detects content
drift inside a single source), the fingerprint is intended to be *stable across
sources*: the same role posted to Greenhouse and a job board should produce the
same fingerprint. We get there with aggressive normalization:

- lowercase everything
- replace all non-alphanumerics with spaces
- collapse whitespace runs
- cap the description before hashing so trivial copy-tweaks don't drift the hash
"""
import hashlib
import re

from app.adapters.models import CanonicalJob

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")

# Only the first N normalized chars of the description go into the fingerprint.
# Full descriptions can be thousands of characters and small reformatting in
# different sources defeats the hash. The first ~800 chars cover the
# role summary and key requirements for most postings.
_DESCRIPTION_CAP = 800


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.lower()
    spaced = _NON_ALNUM.sub(" ", lowered)
    return _WHITESPACE.sub(" ", spaced).strip()


def _primary_location_text(job: CanonicalJob) -> str | None:
    if not job.locations:
        return None
    return job.locations[0].location_text


def compute_fingerprint(job: CanonicalJob) -> str:
    """SHA-256 fingerprint of normalized (title, location, description).

    Company is not part of the hash — fingerprint comparison is always scoped
    to a single company at the dedup query site.
    """
    title = _normalize(job.title)
    location = _normalize(_primary_location_text(job))
    description = _normalize(job.description)[:_DESCRIPTION_CAP]

    joined = f"{title}\x1f{location}\x1f{description}"
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
