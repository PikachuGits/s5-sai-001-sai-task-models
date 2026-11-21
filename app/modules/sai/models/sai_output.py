"""``sai_output`` — versioned output documents of a 招商 AI task.

Each row is an immutable snapshot: ``version`` starts at 1 and increments by
one every time a human edits the output, so the review UI and the write-back
worker can always point at the exact document a person approved.  The unique
index ``(task_id, version) WHERE deleted_at IS NULL`` rejects a duplicate
version and, being partial, still allows an audit-only soft-deleted snapshot.

``output_json`` is JSONB and restricted to an object or an array: a draft is
either a document (object) or a list of line items/paragraphs (array), never a
bare scalar.  ``source`` distinguishes first model output (``ai``) from a
human-edited snapshot (``human_edit``); a human edit must record ``edited_by``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.modules.sai.enums import (
    OUTPUT_SOURCE_ENUM_NAME,
    OutputSource,
)
from app.modules.sai.models.base import (
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum,
)


class SaiOutput(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    """One versioned output snapshot of a 招商 AI task."""

    __tablename__ = "sai_output"

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1 for the first output; +1 on every human edit",
    )
    output_json: Mapped[dict[str, Any] | list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Schema-validated draft document (object) or item list (array)",
    )
    schema_version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Version of the output JSON Schema, e.g. sai.quote_draft.v1",
    )
    source: Mapped[OutputSource] = mapped_column(
        pg_enum(OutputSource, OUTPUT_SOURCE_ENUM_NAME),
        nullable=False,
        comment="ai | human_edit",
    )
    edited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Author of a human edit; NULL for pure model output",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "org_id", "site_id"],
            ["sai_task.id", "sai_task.org_id", "sai_task.site_id"],
            name="fk_sai_output_task_tenant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_sai_output_version_positive",
        ),
        CheckConstraint(
            "jsonb_typeof(output_json) IN ('object', 'array')",
            name="ck_sai_output_output_json_document",
        ),
        CheckConstraint(
            "(source = 'ai' AND edited_by IS NULL) "
            "OR (source = 'human_edit' AND edited_by IS NOT NULL)",
            name="ck_sai_output_source_edited_by",
        ),
        Index(
            "uq_sai_output_task_version",
            "task_id",
            "version",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_sai_output_tenant_task", "org_id", "site_id", "task_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (
            f"SaiOutput(id={self.id!r}, task_id={self.task_id!r}, "
            f"version={self.version!r}, source={self.source!r})"
        )
