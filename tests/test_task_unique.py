"""AC-3: the partial unique index enforces idempotency for live tasks only.

Duplicate ``(org_id, task_type, subject_id, input_hash)`` rows are rejected
while the first row is alive.  Once the first row is soft-deleted the tuple may
be reused, because the index predicate is ``deleted_at IS NULL``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.sai.models import SaiTask
from tests.factories import (
    INPUT_HASH_A,
    INPUT_HASH_B,
    LEAD_ID,
    ORG_A,
    ORG_B,
    SITE_A,
    VISIT_ID,
    make_task,
)


def _count_alive(session) -> int:
    return session.scalar(
        select(func.count()).select_from(SaiTask).where(SaiTask.deleted_at.is_(None))
    )


def test_duplicate_alive_task_is_rejected_by_the_unique_index(session):
    first = make_task()
    session.add(first)
    session.flush()

    second = make_task()
    session.add(second)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    # Prove the rejection came from the intended index, not from the primary key.
    diagnostic = getattr(excinfo.value.orig, "diag", None)
    assert diagnostic is not None
    assert diagnostic.constraint_name == "uq_sai_task_idempotency"

    session.rollback()
    assert _count_alive(session) == 0


def test_same_tuple_after_soft_delete_is_allowed(session):
    first = make_task()
    session.add(first)
    session.flush()

    first.deleted_at = datetime.now(timezone.utc)
    session.flush()

    second = make_task()
    session.add(second)
    session.flush()

    assert _count_alive(session) == 1
    assert session.scalar(select(func.count()).select_from(SaiTask)) == 2
    assert session.scalar(select(func.count()).select_from(SaiTask).where(
        SaiTask.id == first.id
    )) == 1


def test_multiple_soft_deleted_versions_do_not_block_a_new_one(session):
    for _ in range(3):
        task = make_task()
        session.add(task)
        session.flush()
        task.deleted_at = datetime.now(timezone.utc)
        session.flush()

    alive = make_task()
    session.add(alive)
    session.flush()

    assert _count_alive(session) == 1
    assert session.scalar(select(func.count()).select_from(SaiTask)) == 4


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"org_id": ORG_B}, id="different-org"),
        pytest.param({"input_hash": INPUT_HASH_B}, id="different-input-hash"),
        pytest.param({"subject_id": VISIT_ID}, id="different-subject-id"),
        pytest.param({"task_type": "lead_assess"}, id="different-task-type"),
    ],
)
def test_other_tuples_are_allowed(session, overrides):
    first = make_task()
    session.add(first)
    session.flush()

    second = make_task(**overrides)
    session.add(second)
    session.flush()

    assert _count_alive(session) == 2


def test_site_id_is_not_part_of_the_idempotency_tuple(session):
    """The work order fixes the tuple on org/task/subject/hash; site is not in it."""

    first = make_task()
    session.add(first)
    session.flush()

    second = make_task(site_id=uuid.UUID("22222222-2222-2222-2222-333333333333"))
    session.add(second)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert excinfo.value.orig.diag.constraint_name == "uq_sai_task_idempotency"
    session.rollback()


def test_duplicate_is_also_rejected_through_a_second_insert(session):
    """A retried worker inserting two rows in one transaction hits the index."""

    tasks = [make_task(), make_task()]
    for task in tasks:
        session.add(task)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert excinfo.value.orig.diag.constraint_name == "uq_sai_task_idempotency"
    session.rollback()

    # Nothing from the failed batch survives.
    assert session.scalar(select(func.count()).select_from(SaiTask)) == 0


def test_index_is_declared_partial_in_the_model():
    index = next(
        item
        for item in SaiTask.__table__.indexes
        if item.name == "uq_sai_task_idempotency"
    )
    assert index.unique is True
    assert tuple(column.name for column in index.columns) == (
        "org_id",
        "task_type",
        "subject_id",
        "input_hash",
    )
    assert str(index.dialect_options["postgresql"]["where"]) == "deleted_at IS NULL"


def test_identity_columns_come_from_the_shared_contract():
    assert {"id", "org_id", "site_id", "created_at", "created_by", "updated_at", "deleted_at"} <= {
        column.name for column in SaiTask.__table__.columns
    }
    assert ORG_A != ORG_B
    assert LEAD_ID != VISIT_ID
    assert SITE_A is not None
