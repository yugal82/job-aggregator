from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# Import for side effects: registers the pipeline metric families with the
# default Prometheus registry so they appear in /metrics output even before
# any observations have been made. The API and worker are separate processes,
# so families must be declared in the API's import graph too.
from app.observability import metrics as _metrics  # noqa: F401

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
