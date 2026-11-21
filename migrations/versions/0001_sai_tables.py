"""create sai_task and sai_output

Revision ID: 0001_sai_tables
Revises:
Create Date: 2026-11-21 22:00:00

Tables: sai_task, sai_output, plus the five PostgreSQL enum types they use.

Key decisions:

* ``sai_task`` carries ``UNIQUE (id, org_id, site_id)`` so ``sai_output`` can
  use a tenant-aware composite FK ``(task_id, org_id, site_id)`` and cannot
  attach an output to another tenant's task;
* the idempotency rule ``(org_id, task_type, subject_id, input_hash)`` is a
  **partial** unique index filtered by ``deleted_at IS NULL``: a soft-deleted
  task no longer blocks a re-run, while the audit row survives;
* output versions are unique per task and alive row through a second partial
  unique index, so a human edit cannot overwrite history;
* enum types are created before the tables and dropped after them, which keeps
  ``downgrade -1`` clean on PostgreSQL 16.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_sai_tables"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TASK_TYPES = (
    "lead_enrich",
    "lead_assess",
    "lead_dedup",
    "lead_assign",
    "visit_minutes",
    "quote_draft",
    "proposal_draft",
)
SUBJECT_TYPES = ("lead", "visit", "quote", "proposal")
TASK_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "in_review",
    "approved",
    "rejected",
    "written_back",
    "cancelled",
)
REVIEW_LEVELS = ("L1", "L2", "L3")
OUTPUT_SOURCES = ("ai", "human_edit")

TASK_TYPE_ENUM = postgresql.ENUM(*TASK_TYPES, name="sai_task_type", create_type=False)
SUBJECT_TYPE_ENUM = postgresql.ENUM(
    *SUBJECT_TYPES, name="sai_subject_type", create_type=False
)
TASK_STATUS_ENUM = postgresql.ENUM(
    *TASK_STATUSES, name="sai_task_status", create_type=False
)
REVIEW_LEVEL_ENUM = postgresql.ENUM(
    *REVIEW_LEVELS, name="sai_review_level", create_type=False
)
OUTPUT_SOURCE_ENUM = postgresql.ENUM(
    *OUTPUT_SOURCES, name="sai_output_source", create_type=False
)

ENUM_TYPES = (
    TASK_TYPE_ENUM,
    SUBJECT_TYPE_ENUM,
    TASK_STATUS_ENUM,
    REVIEW_LEVEL_ENUM,
    OUTPUT_SOURCE_ENUM,
)


def _create_enum_types() -> None:
    bind = op.get_bind()
    for enum in ENUM_TYPES:
        enum.create(bind, checkfirst=True)


def _drop_enum_types() -> None:
    bind = op.get_bind()
    for enum in reversed(ENUM_TYPES):
        enum.drop(bind, checkfirst=True)


def upgrade() -> None:
    _create_enum_types()

    op.create_table(
        "sai_task",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "task_type",
            TASK_TYPE_ENUM,
            nullable=False,
            comment="lead_enrich | lead_assess | lead_dedup | lead_assign | "
            "visit_minutes | quote_draft | proposal_draft",
        ),
        sa.Column(
            "subject_type",
            SUBJECT_TYPE_ENUM,
            nullable=False,
            comment="lead | visit | quote | proposal",
        ),
        sa.Column(
            "subject_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Id of the lead/visit/quote/proposal owned by another module",
        ),
        sa.Column(
            "status",
            TASK_STATUS_ENUM,
            server_default=sa.text("'queued'::sai_task_status"),
            nullable=False,
            comment="Only the edges in app.modules.sai.state_machine are legal",
        ),
        sa.Column(
            "prompt_key",
            sa.String(length=128),
            nullable=True,
            comment="Prompt registry key, e.g. sai.lead_enrich",
        ),
        sa.Column(
            "prompt_version",
            sa.String(length=64),
            nullable=True,
            comment="Prompt registry version pinned for reproducibility",
        ),
        sa.Column(
            "model_name",
            sa.String(length=128),
            nullable=True,
            comment="Model identifier used for the run; NULL for deterministic tasks",
        ),
        sa.Column(
            "input_hash",
            sa.String(length=64),
            nullable=False,
            comment="Lower-case SHA-256 hex of the normalised task input",
        ),
        sa.Column(
            "review_level",
            REVIEW_LEVEL_ENUM,
            server_default=sa.text("'L1'::sai_review_level"),
            nullable=False,
            comment="L1 | L2 | L3",
        ),
        sa.Column(
            "review_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Review queue item; the review module is an external work order",
        ),
        sa.Column(
            "error_code",
            sa.String(length=64),
            nullable=True,
            comment="Stable machine-readable failure code; NULL while not failed",
        ),
        sa.Column(
            "tokens_in",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Prompt tokens reported by the runtime",
        ),
        sa.Column(
            "tokens_out",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Completion tokens reported by the runtime",
        ),
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
            comment="End-to-end model latency in milliseconds",
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Number of execution attempts; retries increment it",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "org_id", "site_id", name="uq_sai_task_id_tenant"),
        sa.CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name="ck_sai_task_input_hash_sha256",
        ),
        sa.CheckConstraint(
            "(prompt_key IS NULL) = (prompt_version IS NULL)",
            name="ck_sai_task_prompt_pair",
        ),
        sa.CheckConstraint(
            "tokens_in >= 0",
            name="ck_sai_task_tokens_in_non_negative",
        ),
        sa.CheckConstraint(
            "tokens_out >= 0",
            name="ck_sai_task_tokens_out_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_sai_task_latency_non_negative",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_sai_task_attempts_non_negative",
        ),
    )

    op.create_index(
        "uq_sai_task_idempotency",
        "sai_task",
        ["org_id", "task_type", "subject_id", "input_hash"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_sai_task_tenant_status",
        "sai_task",
        ["org_id", "site_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_sai_task_subject",
        "sai_task",
        ["subject_type", "subject_id"],
        unique=False,
    )
    op.create_index(
        "ix_sai_task_review_item",
        "sai_task",
        ["org_id", "review_item_id"],
        unique=False,
        postgresql_where=sa.text("review_item_id IS NOT NULL"),
    )

    op.create_table(
        "sai_output",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            comment="1 for the first output; +1 on every human edit",
        ),
        sa.Column(
            "output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Schema-validated draft document (object) or item list (array)",
        ),
        sa.Column(
            "schema_version",
            sa.String(length=64),
            nullable=False,
            comment="Version of the output JSON Schema, e.g. sai.quote_draft.v1",
        ),
        sa.Column(
            "source",
            OUTPUT_SOURCE_ENUM,
            nullable=False,
            comment="ai | human_edit",
        ),
        sa.Column(
            "edited_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Author of a human edit; NULL for pure model output",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id", "org_id", "site_id"],
            ["sai_task.id", "sai_task.org_id", "sai_task.site_id"],
            name="fk_sai_output_task_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_sai_output_version_positive",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(output_json) IN ('object', 'array')",
            name="ck_sai_output_output_json_document",
        ),
        sa.CheckConstraint(
            "(source = 'ai' AND edited_by IS NULL) "
            "OR (source = 'human_edit' AND edited_by IS NOT NULL)",
            name="ck_sai_output_source_edited_by",
        ),
    )

    op.create_index(
        "uq_sai_output_task_version",
        "sai_output",
        ["task_id", "version"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_sai_output_tenant_task",
        "sai_output",
        ["org_id", "site_id", "task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sai_output_tenant_task", table_name="sai_output")
    op.drop_index(
        "uq_sai_output_task_version",
        table_name="sai_output",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("sai_output")

    op.drop_index(
        "ix_sai_task_review_item",
        table_name="sai_task",
        postgresql_where=sa.text("review_item_id IS NOT NULL"),
    )
    op.drop_index("ix_sai_task_subject", table_name="sai_task")
    op.drop_index("ix_sai_task_tenant_status", table_name="sai_task")
    op.drop_index(
        "uq_sai_task_idempotency",
        table_name="sai_task",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("sai_task")

    _drop_enum_types()
