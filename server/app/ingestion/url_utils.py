"""URL normalization for dedup Level 3.

Strips well-known tracking params, lowercases scheme + host, drops fragment.
Trailing slash normalization: strip on non-root paths only.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "source",
    "gh_src",
    "mc_cid",
    "mc_eid",
    "fbclid",
    "gclid",
}
# NOTE: `gh_jid` is Greenhouse's job identifier used by company redirector
# pages (e.g. https://stripe.com/jobs/search?gh_jid=12345) — it IS the job's
# identity, not tracking. Do NOT add it here or dedup L3 collapses every job
# at that host to one canonical URL.


def normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return None

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query_pairs.sort()

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(query_pairs),
            "",  # drop fragment
        )
    )
