"""Input-hash stability: the contract behind the partial unique index."""

from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select

from app.modules.sai.idempotency import (
    canonical_input,
    compute_input_hash,
    is_valid_input_hash,
)
from app.modules.sai.models import SaiTask
from tests.factories import make_task

WHITELIST = ("company_name", "contact_name", "source_channel")


def _payload(**overrides):
    values = {
        "company_name": "虚构会员企业",
        "contact_name": "虚构联系人",
        "source_channel": "referral",
        "request_id": "trace-1",
        "received_at": "2026-11-21T00:00:00+08:00",
    }
    values.update(overrides)
    return values


def test_hash_is_lowercase_sha256():
    digest = compute_input_hash(_payload(), fields=WHITELIST)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert is_valid_input_hash(digest)
    assert not is_valid_input_hash(digest.upper())
    assert not is_valid_input_hash("abc")


def test_key_order_does_not_change_the_hash():
    first = {"company_name": "虚构会员企业", "contact_name": "虚构联系人"}
    second = {"contact_name": "虚构联系人", "company_name": "虚构会员企业"}

    assert compute_input_hash(first) == compute_input_hash(second)


def test_transport_noise_is_excluded_by_the_whitelist():
    base = _payload()
    noisy = _payload(request_id="trace-2", received_at="2026-11-21T01:00:00+08:00")

    assert compute_input_hash(base, fields=WHITELIST) == compute_input_hash(
        noisy, fields=WHITELIST
    )


def test_business_value_change_changes_the_hash():
    base = compute_input_hash(_payload(), fields=WHITELIST)
    changed = compute_input_hash(
        _payload(contact_name="另一位虚构联系人"), fields=WHITELIST
    )

    assert base != changed


def test_missing_and_explicit_null_hash_the_same():
    assert compute_input_hash({"company_name": "虚构会员企业"}, fields=WHITELIST) == compute_input_hash(
        {"company_name": "虚构会员企业", "contact_name": None, "source_channel": None},
        fields=WHITELIST,
    )


def test_non_json_values_are_hashed_deterministically():
    value = uuid.UUID("11111111-1111-1111-1111-111111111111")

    first = compute_input_hash({"subject_id": value})
    second = compute_input_hash({"subject_id": str(value)})

    assert first == second
    assert len(first) == 64


def test_canonical_input_only_keeps_selected_fields():
    canonical = canonical_input(_payload(), fields=WHITELIST)

    assert set(canonical) == set(WHITELIST)
    assert "request_id" not in canonical
    assert "received_at" not in canonical


def test_computed_hash_is_accepted_by_the_database(session):
    digest = compute_input_hash(_payload(), fields=WHITELIST)
    task = make_task(input_hash=digest)
    session.add(task)
    session.flush()

    assert task.input_hash == digest
    assert session.scalar(select(SaiTask.input_hash).where(SaiTask.id == task.id)) == digest


@pytest.mark.parametrize("payload", [{}, {"company_name": "虚构会员企业"}])
def test_shapes_are_hashable(payload):
    assert len(compute_input_hash(payload, fields=WHITELIST)) == 64
