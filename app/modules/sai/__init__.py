"""招商 AI (SAI) module.

The module currently contains the persistence layer only: the ``sai_task`` and
``sai_output`` models, their Alembic migration and the task status machine.
Downstream workers, prompt registry and the review queue are owned by other
work orders; this delivery deliberately does not import them.
"""

from app.modules.sai.enums import (
    OUTPUT_SOURCES,
    REVIEW_LEVELS,
    SUBJECT_TYPES,
    TASK_STATUSES,
    TASK_TYPES,
    OutputSource,
    ReviewLevel,
    SubjectType,
    TaskStatus,
    TaskType,
)
from app.modules.sai.idempotency import compute_input_hash, is_valid_input_hash
from app.modules.sai.state_machine import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    InvalidTransition,
    allowed_next,
    assert_transition,
    can_transition,
    transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "OUTPUT_SOURCES",
    "REVIEW_LEVELS",
    "SUBJECT_TYPES",
    "TASK_STATUSES",
    "TASK_TYPES",
    "TERMINAL_STATUSES",
    "InvalidTransition",
    "OutputSource",
    "ReviewLevel",
    "SubjectType",
    "TaskStatus",
    "TaskType",
    "allowed_next",
    "assert_transition",
    "can_transition",
    "compute_input_hash",
    "is_valid_input_hash",
    "transition",
]
