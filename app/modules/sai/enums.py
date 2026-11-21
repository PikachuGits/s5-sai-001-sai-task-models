"""Enum value sets fixed by the SAI work order.

``TaskType`` (7 values), ``SubjectType`` (4), ``TaskStatus`` (9) and
``ReviewLevel`` (3) are stored as PostgreSQL native enum types, not free-form
strings, so an out-of-domain value is rejected by the database itself.

The same literal sets are repeated in the Alembic migration because migrations
must not import application modules.  ``tests/test_migration_roundtrip.py``
reads the live ``pg_enum`` catalogue and asserts that the database and these
Python definitions stay identical.

``OutputSource`` distinguishes model output (``ai``) from a row created by a
human edit (``human_edit``).
"""

from __future__ import annotations

from enum import StrEnum


class TaskType(StrEnum):
    """Kind of 招商 AI work item."""

    LEAD_ENRICH = "lead_enrich"
    LEAD_ASSESS = "lead_assess"
    LEAD_DEDUP = "lead_dedup"
    LEAD_ASSIGN = "lead_assign"
    VISIT_MINUTES = "visit_minutes"
    QUOTE_DRAFT = "quote_draft"
    PROPOSAL_DRAFT = "proposal_draft"


class SubjectType(StrEnum):
    """Business object the task is attached to."""

    LEAD = "lead"
    VISIT = "visit"
    QUOTE = "quote"
    PROPOSAL = "proposal"


class TaskStatus(StrEnum):
    """Lifecycle state of a 招商 AI task."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    WRITTEN_BACK = "written_back"
    CANCELLED = "cancelled"


class ReviewLevel(StrEnum):
    """Human review depth required before output can be written back."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class OutputSource(StrEnum):
    """Who produced the output row."""

    AI = "ai"
    HUMAN_EDIT = "human_edit"


TASK_TYPES: tuple[str, ...] = tuple(item.value for item in TaskType)
SUBJECT_TYPES: tuple[str, ...] = tuple(item.value for item in SubjectType)
TASK_STATUSES: tuple[str, ...] = tuple(item.value for item in TaskStatus)
REVIEW_LEVELS: tuple[str, ...] = tuple(item.value for item in ReviewLevel)
OUTPUT_SOURCES: tuple[str, ...] = tuple(item.value for item in OutputSource)

TASK_TYPE_ENUM_NAME = "sai_task_type"
SUBJECT_TYPE_ENUM_NAME = "sai_subject_type"
TASK_STATUS_ENUM_NAME = "sai_task_status"
REVIEW_LEVEL_ENUM_NAME = "sai_review_level"
OUTPUT_SOURCE_ENUM_NAME = "sai_output_source"
