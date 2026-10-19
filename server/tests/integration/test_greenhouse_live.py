"""Live integration test against Stripe's real Greenhouse board.

Run explicitly with:

    pytest -m integration
"""
import pytest

from app.adapters.greenhouse import GreenhouseAdapter
from app.adapters.http import HTTPClient

pytestmark = pytest.mark.integration


async def test_stripe_board_returns_jobs() -> None:
    http = HTTPClient(
        base_url="https://boards-api.greenhouse.io",
        rate_limit_per_second=2.0,
        max_retries=2,
        timeout_seconds=15.0,
    )
    try:
        adapter = GreenhouseAdapter(
            http=http, config={"board_token": "stripe"}, company_slug="stripe"
        )
        raw_jobs = await adapter.discover()
    finally:
        await http.close()

    assert len(raw_jobs) > 0, "Stripe should have at least one open role"

    first = adapter.normalize(raw_jobs[0])
    assert first.title
    assert first.source_provider == "greenhouse"
    assert first.company_slug == "stripe"
    assert first.content_hash
