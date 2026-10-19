from apscheduler.triggers.cron import CronTrigger

from app.models.enums import SyncPriority
from app.workers.tiers import CRON_BY_PRIORITY, cron_for_priority


def test_all_priorities_mapped() -> None:
    for p in SyncPriority:
        assert p in CRON_BY_PRIORITY, f"{p} not mapped to a cron"


def test_cron_expressions_parseable() -> None:
    for cron in CRON_BY_PRIORITY.values():
        # This raises if the expression is malformed.
        CronTrigger.from_crontab(cron)


def test_all_tiers_run_every_six_hours() -> None:
    """Current policy: every priority runs on the same 6-hour cadence
    (``00:00 / 06:00 / 12:00 / 18:00 UTC``). Priority is retained as a
    yaml-visible attribute so we can split the schedule again later
    without touching per-company config."""
    for priority in SyncPriority:
        assert CRON_BY_PRIORITY[priority] == "0 */6 * * *"


def test_unknown_priority_falls_back_to_medium() -> None:
    # cron_for_priority uses .get with medium default; unmapped values reuse it.
    class FakePriority:
        pass

    assert cron_for_priority(FakePriority()) == CRON_BY_PRIORITY[SyncPriority.MEDIUM]  # type: ignore[arg-type]
