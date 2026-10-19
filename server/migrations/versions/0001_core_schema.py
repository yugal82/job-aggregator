"""core schema

Revision ID: 0001
Revises:
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOURCE_TYPE_VALUES = ("official", "ats", "board")
JOB_STATUS_VALUES = ("DISCOVERED", "ACTIVE", "UPDATED", "CLOSED")
SYNC_PRIORITY_VALUES = ("high", "medium", "low")


def upgrade() -> None:
    source_type = postgresql.ENUM(*SOURCE_TYPE_VALUES, name="source_type", create_type=False)
    job_status = postgresql.ENUM(*JOB_STATUS_VALUES, name="job_status", create_type=False)
    sync_priority = postgresql.ENUM(*SYNC_PRIORITY_VALUES, name="sync_priority", create_type=False)

    bind = op.get_bind()
    source_type.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    sync_priority.create(bind, checkfirst=True)

    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("website", sa.String(512)),
        sa.Column("careers_url", sa.String(512)),
        sa.Column("logo_url", sa.String(512)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_companies_slug", "companies", ["slug"], unique=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False, unique=True),
        sa.Column("type", source_type, nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("base_url", sa.String(512)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "company_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("adapter", sa.String(128), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sync_priority, nullable=False, server_default="medium"),
        sa.Column("last_successful_sync", sa.DateTime(timezone=True)),
        sa.Column("last_attempted_sync", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "source_id", name="uq_company_sources_company_source"),
    )
    op.create_index("ix_company_sources_company_id", "company_sources", ["company_id"])
    op.create_index("ix_company_sources_source_id", "company_sources", ["source_id"])

    op.create_table(
        "raw_source_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="SET NULL")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(128)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("response_headers", postgresql.JSONB()),
        sa.Column("content_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_raw_source_documents_source_id", "raw_source_documents", ["source_id"])
    op.create_index("ix_raw_source_documents_company_id", "raw_source_documents", ["company_id"])
    op.create_index("ix_raw_source_documents_content_hash", "raw_source_documents", ["content_hash"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("employment_type", sa.String(64)),
        sa.Column("workplace_type", sa.String(64)),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("salary_min", sa.Numeric(12, 2)),
        sa.Column("salary_max", sa.Numeric(12, 2)),
        sa.Column("salary_currency", sa.String(8)),
        sa.Column("department", sa.String(128)),
        sa.Column("team", sa.String(128)),
        sa.Column("application_url", sa.String(1024)),
        sa.Column("canonical_url", sa.String(1024)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("requisition_id", sa.String(128)),
        sa.Column("status", job_status, nullable=False, server_default="DISCOVERED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_posted_at", "jobs", ["posted_at"])

    op.create_table(
        "job_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_job_id", sa.String(256), nullable=False),
        sa.Column("source_url", sa.String(1024)),
        sa.Column("source_application_url", sa.String(1024)),
        sa.Column("source_title", sa.String(512)),
        sa.Column("source_location", sa.String(512)),
        sa.Column("source_posted_at", sa.DateTime(timezone=True)),
        sa.Column("raw_payload", postgresql.JSONB()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("source_id", "source_job_id", name="uq_job_sources_source_source_job"),
    )
    op.create_index("ix_job_sources_job_id", "job_sources", ["job_id"])
    op.create_index("ix_job_sources_source_id", "job_sources", ["source_id"])

    op.create_table(
        "job_locations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("city", sa.String(128)),
        sa.Column("state", sa.String(128)),
        sa.Column("country", sa.String(128)),
        sa.Column("postal_code", sa.String(32)),
        sa.Column("remote_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hybrid_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("location_text", sa.String(512)),
    )
    op.create_index("ix_job_locations_job_id", "job_locations", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_locations_job_id", table_name="job_locations")
    op.drop_table("job_locations")

    op.drop_index("ix_job_sources_source_id", table_name="job_sources")
    op.drop_index("ix_job_sources_job_id", table_name="job_sources")
    op.drop_table("job_sources")

    op.drop_index("ix_jobs_posted_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_raw_source_documents_content_hash", table_name="raw_source_documents")
    op.drop_index("ix_raw_source_documents_company_id", table_name="raw_source_documents")
    op.drop_index("ix_raw_source_documents_source_id", table_name="raw_source_documents")
    op.drop_table("raw_source_documents")

    op.drop_index("ix_company_sources_source_id", table_name="company_sources")
    op.drop_index("ix_company_sources_company_id", table_name="company_sources")
    op.drop_table("company_sources")

    op.drop_table("sources")

    op.drop_index("ix_companies_slug", table_name="companies")
    op.drop_table("companies")

    bind = op.get_bind()
    postgresql.ENUM(name="sync_priority").drop(bind, checkfirst=True)
    postgresql.ENUM(name="job_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="source_type").drop(bind, checkfirst=True)
