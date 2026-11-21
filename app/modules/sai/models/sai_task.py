"""``sai_task`` — one 招商 AI work item and its execution bookkeeping.

A task is identified for idempotency by the tuple
``(org_id, task_type, subject_id, input_hash)`` while it is alive.  The unique
index carrying that rule is **partial** (``WHERE deleted_at IS NULL``) so a
soft-deleted task no longer blocks a retry with the same input, while the
deleted row itself stays available for audit.

``subject_id`` deliberately has no foreign key: leads, visits, quotes and
proposals live in modules owned by other work orders.  The polymorphic
``subject_type`` + ``subject_id`` pair is the integration point; cross-module
referential integrity is enforced by the owning module, not here.

``prompt_key`` / ``prompt_version`` are nullable together because deterministic
task types (for example ``lead_dedup``) may run without a prompt.  A CHECK
constraint keeps the pair consistent when a prompt is recorded.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.sai.enums import (
    REVIEW_LEVEL_ENUM_NAME,
    SUBJECT_TYPE_ENUM_NAME,
    TASK_STATUS_ENUM_NAME,
    TASK_TYPE_ENUM_NAME,
    ReviewLevel,
    SubjectType,
    TaskStatus,
    TaskType,
)
from app.modules.sai.models.base import (
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum,
)


class SaiTask(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """One queued/running/reviewed AI task in the 招商 AI module."""

    __tablename__ = "sai_task"

    # Re-declared so composite keys in __table_args__ read clearly.
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    task_type: Mapped[TaskType] = mapped_column(
        pg_enum(TaskType, TASK_TYPE_ENUM_NAME),
        nullable=False,
        comment="lead_enrich | lead_assess | lead_dedup | lead_assign | "
        "visit_minutes | quote_draft | proposal_draft",
    )
    subject_type: Mapped[SubjectType] = mapped_column(
        pg_enum(SubjectType, SUBJECT_TYPE_ENUM_NAME),
        nullable=False,
        comment="lead | visit | quote | proposal",
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        comment="Id of the lead/visit/quote/proposal owned by another module",
    )

    status: Mapped[TaskStatus] = mapped_column(
        pg_enum(TaskStatus, TASK_STATUS_ENUM_NAME),
        nullable=False,
        default=TaskStatus.QUEUED,
        server_default=text("'queued'::sai_task_status"),
        comment="Only the edges in app.modules.sai.state_machine are legal",
    )

    prompt_key: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Prompt registry key, e.g. sai.lead_enrich",
    )
    prompt_version: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Prompt registry version pinned for reproducibility",
    )
    model_name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Model identifier used for the run; NULL for deterministic tasks",
    )
    input_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Lower-case SHA-256 hex of the normalised task input",
    )

    review_level: Mapped[ReviewLevel] = mapped_column(
        pg_enum(ReviewLevel, REVIEW_LEVEL_ENUM_NAME),
        nullable=False,
        default=ReviewLevel.L1,
        server_default=text("'L1'::sai_review_level"),
        comment="L1 | L2 | L3",
    )
    review_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Review queue item; the review module is an external work order",
    )

    error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Stable machine-readable failure code; NULL while not failed",
    )
    tokens_in: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Prompt tokens reported by the runtime",
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Completion tokens reported by the runtime",
    )
    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="End-to-end model latency in milliseconds",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Number of execution attempts; retries increment it",
    )

    __table_args__ = (
        # Needed as the parent key of the tenant-aware composite FK from
        # sai_output: a child row may only reference a task of the same tenant.
        UniqueConstraint(
            "id",
            "org_id",
            "site_id",
            name="uq_sai_task_id_tenant",
        ),
        CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name="ck_sai_task_input_hash_sha256",
        ),
        CheckConstraint(
            "(prompt_key IS NULL) = (prompt_version IS NULL)",
            name="ck_sai_task_prompt_pair",
        ),
        CheckConstraint(
            "tokens_in >= 0",
            name="ck_sai_task_tokens_in_non_negative",
        ),
        CheckConstraint(
            "tokens_out >= 0",
            name="ck_sai_task_tokens_out_non_negative",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_sai_task_latency_non_negative",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="ck_sai_task_attempts_non_negative",
        ),
        Index(
            "uq_sai_task_idempotency",
            "org_id",
            "task_type",
            "subject_id",
            "input_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_sai_task_tenant_status", "org_id", "site_id", "status"),
        Index("ix_sai_task_subject", "subject_type", "subject_id"),
        Index(
            "ix_sai_task_review_item",
            "org_id",
            "review_item_id",
            postgresql_where=text("review_item_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"SaiTask(id={self.id!r}, task_type={self.task_type!r}, "
            f"subject_id={self.subject_id!r}, status={self.status!r})"
        )
