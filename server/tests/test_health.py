from httpx import AsyncClient


async def test_health_is_cheap_and_dependency_free(client: AsyncClient) -> None:
    """``/health`` is the liveness probe — must respond 200 as soon as the
    ASGI app is up, regardless of DB state."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_pings_the_database(client: AsyncClient) -> None:
    """``/ready`` is the readiness probe — includes a DB round-trip so
    deploy pipelines can gate release on it."""
    response = await client.get("/ready")
    assert response.status_code == 200

    body = response.json()
    assert set(body.keys()) == {"status", "database"}
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] in {"ok", "error"}
