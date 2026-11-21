"""Column mixins implementing the project's cross-module table conventions.

Every business table in this delivery carries ``id (UUID)``, ``org_id``,
``site_id``, ``created_at``, ``created_by``, ``updated_at`` and ``deleted_at``
(soft delete), as required by the project's unified technical agreement.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def pg_enum(enum_class, name: str) -> Enum:
    """Build a native PostgreSQL enum that stores enum *values*, not names."""

    return Enum(
        enum_class,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )


class UUIDPrimaryKeyMixin:
    """UUID primary key with both a Python-side and a database-side default."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TenantMixin:
    """Mandatory tenant scope shared by every business table."""

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class TimestampMixin:
    """Audit and soft-delete columns required by the project conventions."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
