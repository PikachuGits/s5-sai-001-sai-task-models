"""Model-level tests: defaults, enum domains, check constraints and outputs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DataError, IntegrityError

from app.modules.sai.enums import OutputSource, ReviewLevel, SubjectType, TaskStatus, TaskType
from app.modules.sai.models import SaiOutput, SaiTask
from app.modules.sai.versions import next_output_version
from tests.factories import (
    EDITOR_ID,
    INPUT_HASH_A,
    ORG_A,
    SITE_A,
    make_output,
    make_task,
)


def _constraint_name(excinfo: pytest.ExceptionInfo[IntegrityError]) -> str | None:
    diagnostic = getattr(excinfo.value.orig, "diag", None)
    return None if diagnostic is None else diagnostic.constraint_name


def test_task_defaults_are_applied_by_the_database(session):
    task = make_task()
    session.add(task)
    session.flush()
    session.refresh(task)

    assert isinstance(task.id, uuid.UUID)
    assert task.status == TaskStatus.QUEUED
    assert task.review_level == ReviewLevel.L1
    assert task.tokens_in == 0
    assert task.tokens_out == 0
    assert task.attempts == 0
    assert task.created_at is not None
    assert task.updated_at is not None
    assert task.deleted_at is None
    assert task.created_by is None


def test_enum_columns_store_values_not_names(session):
    task = make_task(
        task_type=TaskType.QUOTE_DRAFT,
        subject_type=SubjectType.QUOTE,
    )
    session.add(task)
    session.flush()

    row = session.execute(
        select(
            text("task_type::text"),
            text("subject_type::text"),
            text("status::text"),
            text("review_level::text"),
        ).select_from(SaiTask).where(SaiTask.id == task.id)
    ).one()

    assert row[0] == "quote_draft"
    assert row[1] == "quote"
    assert row[2] == "queued"
    assert row[3] == "L1"
    # Reading through the ORM returns the Python enum member.
    assert isinstance(task.task_type, TaskType)


def test_all_task_types_are_available(session):
    for index, task_type in enumerate(TaskType):
        subject_type = list(SubjectType)[index % len(SubjectType)]
        task = make_task(
            task_type=task_type,
            subject_type=subject_type,
            subject_id=uuid.uuid4(),
            input_hash=f"{index:064x}",
        )
        session.add(task)
    session.flush()

    stored = {
        row[0]
        for row in session.execute(select(text("task_type::text")).select_from(SaiTask))
    }
    assert stored == {item.value for item in TaskType}


@pytest.mark.parametrize(
    "bad_hash",
    [
        "",
        "abc",
        "a" * 63,
        "A" * 64,
        "z" * 64,
    ],
)
def test_input_hash_must_be_lowercase_sha256_hex(session, bad_hash):
    task = make_task(input_hash=bad_hash)
    session.add(task)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_task_input_hash_sha256"
    session.rollback()


def test_input_hash_column_is_bounded_to_64_characters(session):
    task = make_task(input_hash="a" * 65)
    session.add(task)

    with pytest.raises(DataError) as excinfo:
        session.flush()

    assert "value too long" in str(excinfo.value)
    session.rollback()


def test_prompt_key_and_version_must_be_set_together(session):
    task = make_task(prompt_key="sai.lead_enrich", prompt_version=None)
    session.add(task)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_task_prompt_pair"
    session.rollback()


def test_prompt_pair_can_be_absent_for_deterministic_tasks(session):
    task = make_task(
        task_type=TaskType.LEAD_DEDUP,
        prompt_key=None,
        prompt_version=None,
        model_name=None,
    )
    session.add(task)
    session.flush()

    assert task.prompt_key is None
    assert task.model_name is None


@pytest.mark.parametrize(
    "field,value,constraint",
    [
        ("tokens_in", -1, "ck_sai_task_tokens_in_non_negative"),
        ("tokens_out", -1, "ck_sai_task_tokens_out_non_negative"),
        ("latency_ms", -5, "ck_sai_task_latency_non_negative"),
        ("attempts", -1, "ck_sai_task_attempts_non_negative"),
    ],
)
def test_non_negative_counters(session, field, value, constraint):
    task = make_task(**{field: value})
    session.add(task)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == constraint
    session.rollback()


def test_latency_may_be_null(session):
    task = make_task(latency_ms=None, tokens_in=12, tokens_out=34, attempts=1)
    session.add(task)
    session.flush()

    assert task.latency_ms is None
    assert task.tokens_in == 12
    assert task.tokens_out == 34
    assert task.attempts == 1


def test_output_version_is_one_on_first_insert(session):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, version=next_output_version([]))
    session.add(output)
    session.flush()

    assert output.version == 1
    assert task.status == TaskStatus.QUEUED


def test_next_output_version_increments_by_one():
    assert next_output_version([]) == 1
    assert next_output_version([1]) == 2
    assert next_output_version([1, 2, 3]) == 4
    assert next_output_version([2, 7, 5]) == 8


def test_ai_output_must_not_name_an_editor(session):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, source=OutputSource.AI, edited_by=EDITOR_ID)
    session.add(output)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_output_source_edited_by"
    session.rollback()


def test_human_edit_must_name_an_editor(session):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, version=2, source=OutputSource.HUMAN_EDIT, edited_by=None)
    session.add(output)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_output_source_edited_by"
    session.rollback()


def test_human_edit_with_editor_is_accepted(session):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(
        task,
        version=2,
        source=OutputSource.HUMAN_EDIT,
        edited_by=EDITOR_ID,
        output_json=["fictional paragraph one", "fictional paragraph two"],
    )
    session.add(output)
    session.flush()

    assert output.source == OutputSource.HUMAN_EDIT
    assert output.edited_by == EDITOR_ID


@pytest.mark.parametrize("payload", ["plain text", 42, True, None])
def test_output_json_must_be_a_document(session, payload):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, output_json=payload)
    session.add(output)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_output_output_json_document"
    session.rollback()


def test_output_json_accepts_object_and_array(session):
    task = make_task()
    session.add(task)
    session.flush()

    session.add(make_output(task, version=1, output_json={"nodes": []}))
    session.add(make_output(task, version=2, output_json=[{"line": 1}]))
    session.flush()

    assert session.scalar(select(func.count()).select_from(SaiOutput)) == 2


@pytest.mark.parametrize("version", [0, -1])
def test_output_version_must_be_positive(session, version):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, version=version)
    session.add(output)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "ck_sai_output_version_positive"
    session.rollback()


def test_duplicate_alive_output_version_is_rejected(session):
    task = make_task()
    session.add(task)
    session.flush()

    session.add(make_output(task, version=1))
    session.flush()

    session.add(make_output(task, version=1))

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "uq_sai_output_task_version"
    session.rollback()


def test_output_version_can_be_reused_after_soft_delete(session):
    task = make_task()
    session.add(task)
    session.flush()

    first = make_output(task, version=1)
    session.add(first)
    session.flush()
    first.deleted_at = datetime.now(timezone.utc)
    session.flush()

    replacement = make_output(task, version=1)
    session.add(replacement)
    session.flush()

    alive = session.scalars(
        select(SaiOutput).where(
            SaiOutput.task_id == task.id,
            SaiOutput.version == 1,
            SaiOutput.deleted_at.is_(None),
        )
    ).all()
    assert len(alive) == 1
    assert session.scalar(select(func.count()).select_from(SaiOutput)) == 2


def test_output_is_bound_to_the_task_tenant(session):
    task = make_task()
    session.add(task)
    session.flush()

    output = make_output(task, org_id=uuid.UUID("11111111-1111-1111-1111-333333333333"))
    session.add(output)

    with pytest.raises(IntegrityError) as excinfo:
        session.flush()

    assert _constraint_name(excinfo) == "fk_sai_output_task_tenant"
    session.rollback()


def test_deleting_the_task_cascades_to_its_outputs(session):
    task = make_task()
    session.add(task)
    session.flush()

    session.add(make_output(task, version=1))
    session.add(make_output(task, version=2, output_json={"summary": "edited"}))
    session.flush()

    session.delete(task)
    session.flush()

    assert session.scalar(select(func.count()).select_from(SaiTask)) == 0
    assert session.scalar(select(func.count()).select_from(SaiOutput)) == 0


def test_shared_columns_exist_on_both_tables():
    shared = {"id", "org_id", "site_id", "created_at", "created_by", "updated_at", "deleted_at"}
    assert shared <= {column.name for column in SaiTask.__table__.columns}
    assert shared <= {column.name for column in SaiOutput.__table__.columns}
    assert ORG_A is not None and SITE_A is not None and INPUT_HASH_A is not None
