from httpx import AsyncClient


async def test_metrics_endpoint_returns_prometheus_text(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    # These names are exported by app/observability/metrics.py at import time,
    # so they should appear in the exposition even before any values are set.
    assert "jobs_fetched_total" in body
    assert "source_failures_total" in body
    assert "sync_duration_seconds" in body
