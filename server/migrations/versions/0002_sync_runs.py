"""sync_runs table + jobs.consecutive_missed_syncs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYNC_RUN_STATUS_VALUES = ("running", "success", "failed")


def upgrade() -> None:
    sync_run_status = postgresql.ENUM(
        *SYNC_RUN_STATUS_VALUES, name="sync_run_status", create_type=False
    )
    sync_run_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "jobs",
        sa.Column(
            "consecutive_missed_syncs",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "company_source_id",
            sa.Integer(),
            sa.ForeignKey("company_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adapter", sa.String(128), nullable=False),
        sa.Column("status", sync_run_status, nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_closed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_sync_runs_company_source_id", "sync_runs", ["company_source_id"])
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_index("ix_sync_runs_company_source_id", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_column("jobs", "consecutive_missed_syncs")
    postgresql.ENUM(name="sync_run_status").drop(op.get_bind(), checkfirst=True)
