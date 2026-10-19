import pytest

from app.ingestion.url_utils import normalize_url


@pytest.mark.parametrize(
    "given, expected",
    [
        (None, None),
        ("", None),
        ("not a url", None),
        ("https://example.com/jobs/123", "https://example.com/jobs/123"),
        (
            "https://Example.COM/Jobs/123?utm_source=x&utm_medium=y&ref=z",
            "https://example.com/Jobs/123",
        ),
        (
            "https://example.com/jobs/123?keep=this&utm_campaign=y",
            "https://example.com/jobs/123?keep=this",
        ),
        (
            "https://example.com/jobs/123#apply",
            "https://example.com/jobs/123",
        ),
        (
            "https://example.com/jobs/123/",
            "https://example.com/jobs/123",
        ),
        (
            "https://example.com/",
            "https://example.com/",
        ),
        (
            # gh_jid is Greenhouse's job identifier on redirector pages — it
            # must be preserved, otherwise every job at the same host collapses
            # to a single canonical URL and dedup L3 mismatches them all.
            "https://stripe.com/jobs/search?gh_jid=8172487",
            "https://stripe.com/jobs/search?gh_jid=8172487",
        ),
    ],
)
def test_normalize_url(given, expected):
    assert normalize_url(given) == expected


def test_normalize_url_sorts_remaining_query_params():
    assert (
        normalize_url("https://example.com/jobs?z=1&a=2&utm_source=x")
        == "https://example.com/jobs?a=2&z=1"
    )


def test_normalize_url_keeps_job_identifiers_distinct():
    a = normalize_url("https://stripe.com/jobs/search?gh_jid=1")
    b = normalize_url("https://stripe.com/jobs/search?gh_jid=2")
    assert a != b
