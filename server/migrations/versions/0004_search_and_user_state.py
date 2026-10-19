"""users, job_user_states, jobs.search_vector + GIN

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_JOB_STATE_VALUES = (
    "VIEWED",
    "SAVED",
    "APPLIED",
    "INTERVIEW",
    "REJECTED",
    "OFFER",
    "WITHDRAWN",
    "DISMISSED",
)

_SEARCH_VECTOR_EXPR = (
    "setweight(to_tsvector('english', coalesce(canonical_title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(description, '')), 'B')"
)


def upgrade() -> None:
    user_job_state = postgresql.ENUM(
        *USER_JOB_STATE_VALUES, name="user_job_state", create_type=False
    )
    user_job_state.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "job_user_states",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", user_job_state, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "job_id", name="uq_job_user_states_user_job"),
    )
    op.create_index("ix_job_user_states_user_id", "job_user_states", ["user_id"])
    op.create_index("ix_job_user_states_job_id", "job_user_states", ["job_id"])

    # jobs.search_vector as a Postgres GENERATED STORED tsvector column.
    # Not every DDL dialect supports GENERATED in op.add_column, so we use
    # a raw ALTER statement.
    op.execute(
        f"ALTER TABLE jobs ADD COLUMN search_vector tsvector "
        f"GENERATED ALWAYS AS ({_SEARCH_VECTOR_EXPR}) STORED"
    )
    op.execute("CREATE INDEX ix_jobs_search_vector ON jobs USING GIN (search_vector)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_search_vector")
    op.drop_column("jobs", "search_vector")

    op.drop_index("ix_job_user_states_job_id", table_name="job_user_states")
    op.drop_index("ix_job_user_states_user_id", table_name="job_user_states")
    op.drop_table("job_user_states")
    op.drop_table("users")

    postgresql.ENUM(name="user_job_state").drop(op.get_bind(), checkfirst=True)
