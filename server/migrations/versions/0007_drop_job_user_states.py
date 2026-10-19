"""Drop job_user_states + user_job_state enum.

The application-tracking feature was removed (see Phase 14 — the portal
is a read-only job aggregator now; users submit applications through
each company's own ATS). This drops the table + enum. ``users`` and
``user_profiles`` stay because /api/recommendations still consumes
``user_profiles`` for optional match scoring.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-17
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("job_user_states")
    op.execute("DROP TYPE IF EXISTS user_job_state")


def downgrade() -> None:
    # Intentionally not restoring the table — this feature is removed, not
    # paused. If anyone needs it back, reinstate 0004's upgrade manually.
    raise NotImplementedError(
        "0007 is a one-way drop; restore 0004 by hand if you really need it"
    )
