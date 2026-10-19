"""jobs.level

Adds a nullable ``level`` string column to ``jobs`` so adapters can
populate the source-native career-level token (e.g. Microsoft's
``IC2``/``IC3``/..., Google's ``L3``, Amazon's ``SDE II``). Case-
insensitive filter query lives on ``/api/jobs?level=...``.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("level", sa.String(length=32), nullable=True),
    )
    # Lower-case index so case-insensitive matches hit the index.
    op.execute(
        "CREATE INDEX ix_jobs_level_lower ON jobs (lower(level)) WHERE level IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_level_lower")
    op.drop_column("jobs", "level")
