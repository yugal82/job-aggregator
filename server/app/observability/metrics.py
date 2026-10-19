"""Prometheus metrics for the ingestion pipeline.

Counters and histograms live in the default global registry, which the
FastAPI ``/metrics`` endpoint scrapes via ``generate_latest``. The scheduler
increments these as syncs run; the API just exposes them.
"""
from prometheus_client import Counter, Histogram

JOBS_FETCHED_TOTAL = Counter(
    "jobs_fetched_total",
    "Number of raw jobs returned by adapter.discover() over the process lifetime.",
    labelnames=("provider", "company"),
)

SOURCE_FAILURES_TOTAL = Counter(
    "source_failures_total",
    "Number of scheduled syncs that raised before completing.",
    labelnames=("provider", "company", "reason"),
)

SYNC_DURATION_SECONDS = Histogram(
    "sync_duration_seconds",
    "Wall-clock duration of a scheduled sync, from lock acquisition to return.",
    labelnames=("provider", "company"),
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300, 600),
)

SYNC_SKIPPED_TOTAL = Counter(
    "sync_skipped_total",
    "Scheduled syncs skipped because another worker held the lock.",
    labelnames=("provider", "company"),
)
