"""jobs.fingerprint + job_versions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("fingerprint", sa.String(64)))
    op.create_index("ix_jobs_fingerprint", "jobs", ["fingerprint"])

    op.create_table(
        "job_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("employment_type", sa.String(64)),
        sa.Column("workplace_type", sa.String(64)),
        sa.Column("department", sa.String(128)),
        sa.Column("team", sa.String(128)),
        sa.Column("salary_min", sa.Numeric(12, 2)),
        sa.Column("salary_max", sa.Numeric(12, 2)),
        sa.Column("salary_currency", sa.String(8)),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("job_id", "version", name="uq_job_versions_job_version"),
    )
    op.create_index("ix_job_versions_job_id", "job_versions", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_versions_job_id", table_name="job_versions")
    op.drop_table("job_versions")
    op.drop_index("ix_jobs_fingerprint", table_name="jobs")
    op.drop_column("jobs", "fingerprint")
