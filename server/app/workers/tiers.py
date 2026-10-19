"""Priority tier → cron expression mapping used by the scheduler.

Current policy: every tier runs **every 6 hours on the hour**
(``00:00, 06:00, 12:00, 18:00 UTC`` — four times a day). Priority is
kept as a yaml-visible attribute so we can diverge again later without
touching every company's config.
"""
from app.models.enums import SyncPriority

_EVERY_6_HOURS = "0 */6 * * *"

CRON_BY_PRIORITY: dict[SyncPriority, str] = {
    SyncPriority.HIGH: _EVERY_6_HOURS,
    SyncPriority.MEDIUM: _EVERY_6_HOURS,
    SyncPriority.LOW: _EVERY_6_HOURS,
}


def cron_for_priority(priority: SyncPriority) -> str:
    return CRON_BY_PRIORITY.get(priority, CRON_BY_PRIORITY[SyncPriority.MEDIUM])
