"""Fictional factories for the SAI persistence tests.

All identifiers and payloads are made-up UUIDs and neutral text; the suite never
uses real people, companies or customer data.
"""

from __future__ import annotations

import uuid

from app.modules.sai.enums import OutputSource, ReviewLevel, SubjectType, TaskStatus, TaskType
from app.modules.sai.models import SaiOutput, SaiTask

ORG_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
ORG_B = uuid.UUID("11111111-1111-1111-1111-222222222222")
SITE_A = uuid.UUID("22222222-2222-2222-2222-111111111111")
SITE_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
LEAD_ID = uuid.UUID("33333333-3333-3333-3333-111111111111")
VISIT_ID = uuid.UUID("33333333-3333-3333-3333-222222222222")
EDITOR_ID = uuid.UUID("44444444-4444-4444-4444-111111111111")

INPUT_HASH_A = "a" * 64
INPUT_HASH_B = "b" * 64


def make_task(**overrides) -> SaiTask:
    """Build an unsaved ``sai_task`` with valid defaults."""

    values = {
        "org_id": ORG_A,
        "site_id": SITE_A,
        "task_type": TaskType.LEAD_ENRICH,
        "subject_type": SubjectType.LEAD,
        "subject_id": LEAD_ID,
        "input_hash": INPUT_HASH_A,
        "prompt_key": "sai.lead_enrich",
        "prompt_version": "v1",
        "model_name": "fiction-model-1",
        "review_level": ReviewLevel.L1,
    }
    values.update(overrides)
    return SaiTask(**values)


def make_output(task: SaiTask, **overrides) -> SaiOutput:
    """Build an unsaved ``sai_output`` attached to ``task``'s tenant."""

    values = {
        "org_id": task.org_id,
        "site_id": task.site_id,
        "task_id": task.id,
        "version": 1,
        "output_json": {"summary": "fictional draft", "items": []},
        "schema_version": "sai.lead_enrich.v1",
        "source": OutputSource.AI,
        "edited_by": None,
    }
    values.update(overrides)
    return SaiOutput(**values)


def status_task(status: TaskStatus | str) -> SaiTask:
    """Build an unsaved task in a given status for pure state-machine tests."""

    task = make_task()
    task.status = status
    return task
