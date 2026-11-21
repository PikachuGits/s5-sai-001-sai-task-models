"""AC-1: migration round-trip, schema shape, enum domains and zero drift.

``alembic upgrade head`` -> ``alembic downgrade -1`` -> ``alembic upgrade head``
must all succeed on PostgreSQL 16, and ``alembic check`` must report no new
upgrade operations afterwards.
"""

from __future__ import annotations

from alembic import command
from sqlalchemy import inspect, text

EXPECTED_TASK_COLUMNS = {
    "id",
    "org_id",
    "site_id",
    "task_type",
    "subject_type",
    "subject_id",
    "status",
    "prompt_key",
    "prompt_version",
    "model_name",
    "input_hash",
    "review_level",
    "review_item_id",
    "error_code",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "attempts",
    "created_at",
    "created_by",
    "updated_at",
    "deleted_at",
}

EXPECTED_OUTPUT_COLUMNS = {
    "id",
    "org_id",
    "site_id",
    "task_id",
    "version",
    "output_json",
    "schema_version",
    "source",
    "edited_by",
    "created_at",
    "created_by",
    "updated_at",
    "deleted_at",
}

DELIVERY_TABLES = {"sai_task", "sai_output"}

EXPECTED_ENUMS = {
    "sai_task_type": {
        "lead_enrich",
        "lead_assess",
        "lead_dedup",
        "lead_assign",
        "visit_minutes",
        "quote_draft",
        "proposal_draft",
    },
    "sai_subject_type": {"lead", "visit", "quote", "proposal"},
    "sai_task_status": {
        "queued",
        "running",
        "succeeded",
        "failed",
        "in_review",
        "approved",
        "rejected",
        "written_back",
        "cancelled",
    },
    "sai_review_level": {"L1", "L2", "L3"},
    "sai_output_source": {"ai", "human_edit"},
}


def _columns(engine, table: str) -> dict:
    return {column["name"]: column for column in inspect(engine).get_columns(table)}


def test_tables_and_revision_are_applied(engine):
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert DELIVERY_TABLES <= tables
    assert "alembic_version" in tables

    with engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert revision == "0001_sai_tables"


def test_enum_types_have_the_exact_domains(engine):
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT t.typname, e.enumlabel "
                "FROM pg_type t JOIN pg_enum e ON t.oid = e.enumtypid "
                "WHERE t.typname = ANY(:names) "
                "ORDER BY t.typname, e.enumsortorder"
            ),
            {"names": list(EXPECTED_ENUMS)},
        ).all()

    observed: dict[str, list[str]] = {}
    for type_name, label in rows:
        observed.setdefault(type_name, []).append(label)

    assert set(observed) == set(EXPECTED_ENUMS)
    for type_name, expected in EXPECTED_ENUMS.items():
        assert set(observed[type_name]) == expected
        assert len(observed[type_name]) == len(expected)


def test_task_columns_and_types(engine):
    columns = _columns(engine, "sai_task")
    assert set(columns) == EXPECTED_TASK_COLUMNS

    assert columns["id"]["type"].__class__.__name__ == "UUID"
    assert columns["id"]["nullable"] is False
    assert "gen_random_uuid" in str(columns["id"]["default"])
    assert columns["org_id"]["nullable"] is False
    assert columns["site_id"]["nullable"] is False

    assert columns["task_type"]["type"].__class__.__name__ == "ENUM"
    assert columns["task_type"]["type"].name == "sai_task_type"
    assert columns["subject_type"]["type"].name == "sai_subject_type"
    assert columns["status"]["type"].name == "sai_task_status"
    assert columns["review_level"]["type"].name == "sai_review_level"

    assert columns["subject_id"]["nullable"] is False
    assert columns["status"]["nullable"] is False
    assert "queued" in str(columns["status"]["default"])
    assert columns["review_level"]["nullable"] is False
    assert "L1" in str(columns["review_level"]["default"])

    assert columns["prompt_key"]["type"].length == 128
    assert columns["prompt_key"]["nullable"] is True
    assert columns["prompt_version"]["type"].length == 64
    assert columns["prompt_version"]["nullable"] is True
    assert columns["model_name"]["type"].length == 128
    assert columns["model_name"]["nullable"] is True

    assert columns["input_hash"]["type"].length == 64
    assert columns["input_hash"]["nullable"] is False

    assert columns["review_item_id"]["nullable"] is True
    assert columns["error_code"]["type"].length == 64
    assert columns["error_code"]["nullable"] is True

    assert columns["tokens_in"]["nullable"] is False
    assert str(columns["tokens_in"]["default"]) == "0"
    assert columns["tokens_out"]["nullable"] is False
    assert str(columns["tokens_out"]["default"]) == "0"
    assert columns["latency_ms"]["nullable"] is True
    assert columns["attempts"]["nullable"] is False
    assert str(columns["attempts"]["default"]) == "0"

    assert columns["created_at"]["nullable"] is False
    assert columns["created_by"]["nullable"] is True
    assert columns["updated_at"]["nullable"] is False
    assert columns["deleted_at"]["nullable"] is True


def test_output_columns_and_types(engine):
    columns = _columns(engine, "sai_output")
    assert set(columns) == EXPECTED_OUTPUT_COLUMNS

    assert columns["id"]["type"].__class__.__name__ == "UUID"
    assert columns["task_id"]["nullable"] is False
    assert columns["version"]["type"].__class__.__name__ == "INTEGER"
    assert columns["version"]["nullable"] is False
    assert columns["output_json"]["type"].__class__.__name__ == "JSONB"
    assert columns["output_json"]["nullable"] is False
    assert columns["schema_version"]["type"].length == 64
    assert columns["schema_version"]["nullable"] is False
    assert columns["source"]["type"].name == "sai_output_source"
    assert columns["source"]["nullable"] is False
    assert columns["edited_by"]["nullable"] is True
    assert columns["created_at"]["nullable"] is False
    assert columns["created_by"]["nullable"] is True
    assert columns["updated_at"]["nullable"] is False
    assert columns["deleted_at"]["nullable"] is True


def test_check_constraint_names(engine):
    inspector = inspect(engine)

    assert {
        "ck_sai_task_input_hash_sha256",
        "ck_sai_task_prompt_pair",
        "ck_sai_task_tokens_in_non_negative",
        "ck_sai_task_tokens_out_non_negative",
        "ck_sai_task_latency_non_negative",
        "ck_sai_task_attempts_non_negative",
    } <= {
        constraint["name"]
        for constraint in inspector.get_check_constraints("sai_task")
    }

    assert {
        "ck_sai_output_version_positive",
        "ck_sai_output_output_json_document",
        "ck_sai_output_source_edited_by",
    } <= {
        constraint["name"]
        for constraint in inspector.get_check_constraints("sai_output")
    }


def test_task_unique_constraints(engine):
    inspector = inspect(engine)
    unique = inspector.get_unique_constraints("sai_task")
    assert any(
        constraint["name"] == "uq_sai_task_id_tenant"
        and set(constraint["column_names"]) == {"id", "org_id", "site_id"}
        for constraint in unique
    )


def test_task_indexes(engine):
    inspector = inspect(engine)
    indexes = {
        index["name"]: index for index in inspector.get_indexes("sai_task")
    }

    assert {
        "uq_sai_task_idempotency",
        "ix_sai_task_tenant_status",
        "ix_sai_task_subject",
        "ix_sai_task_review_item",
    } <= set(indexes)

    idempotency = indexes["uq_sai_task_idempotency"]
    assert idempotency["unique"] is True
    assert tuple(idempotency["column_names"]) == (
        "org_id",
        "task_type",
        "subject_id",
        "input_hash",
    )


def test_output_indexes(engine):
    inspector = inspect(engine)
    indexes = {
        index["name"]: index for index in inspector.get_indexes("sai_output")
    }

    assert {"uq_sai_output_task_version", "ix_sai_output_tenant_task"} <= set(indexes)
    assert indexes["uq_sai_output_task_version"]["unique"] is True
    assert tuple(indexes["uq_sai_output_task_version"]["column_names"]) == (
        "task_id",
        "version",
    )


def test_partial_index_predicates_are_present(engine):
    with engine.connect() as connection:
        definitions = dict(
            connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' "
                    "AND tablename IN ('sai_task', 'sai_output')"
                )
            ).all()
        )

    assert "WHERE (deleted_at IS NULL)" in definitions["uq_sai_task_idempotency"]
    assert "deleted_at IS NULL" in definitions["uq_sai_output_task_version"]
    assert "review_item_id IS NOT NULL" in definitions["ix_sai_task_review_item"]


def test_foreign_key_is_tenant_aware(engine):
    inspector = inspect(engine)
    foreign_keys = inspector.get_foreign_keys("sai_output")
    assert len(foreign_keys) == 1

    foreign_key = foreign_keys[0]
    assert foreign_key["name"] == "fk_sai_output_task_tenant"
    assert foreign_key["constrained_columns"] == ["task_id", "org_id", "site_id"]
    assert foreign_key["referred_table"] == "sai_task"
    assert foreign_key["referred_columns"] == ["id", "org_id", "site_id"]
    assert foreign_key["options"].get("ondelete") == "CASCADE"


def test_upgrade_downgrade_one_upgrade_and_zero_drift(engine, alembic_config):
    """AC-1 evidence: both directions run and ``alembic check`` is clean."""

    assert DELIVERY_TABLES <= set(inspect(engine).get_table_names())

    command.downgrade(alembic_config, "-1")

    inspector = inspect(engine)
    assert not (DELIVERY_TABLES & set(inspector.get_table_names()))

    with engine.connect() as connection:
        remaining_enum_types = connection.execute(
            text(
                "SELECT count(*) FROM pg_type WHERE typname = ANY(:names)"
            ),
            {"names": list(EXPECTED_ENUMS)},
        ).scalar_one()
    assert remaining_enum_types == 0

    command.upgrade(alembic_config, "head")

    inspector = inspect(engine)
    assert DELIVERY_TABLES <= set(inspector.get_table_names())

    # Raises ``AutogenerateDiffsDetected`` when metadata and the migrated
    # schema disagree; a clean run is the acceptance evidence for zero drift.
    command.check(alembic_config)
