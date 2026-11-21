"""AC-2: the status machine covers every legal edge and rejects illegal ones.

The expected edge table is written out literally so a future edit of the
implementation cannot silently redefine the contract the buyer reviewed.
"""

from __future__ import annotations

from itertools import product

import pytest

from app.modules.sai.enums import TASK_STATUSES, TaskStatus
from app.modules.sai.state_machine import (
    ALLOWED_TRANSITIONS,
    LEGAL_EDGE_COUNT,
    TERMINAL_STATUSES,
    InvalidTransition,
    allowed_next,
    can_transition,
    assert_transition,
    iter_legal_edges,
    reachable_statuses,
    transition,
)
from tests.factories import status_task

EXPECTED_EDGES = {
    ("queued", "running"),
    ("queued", "cancelled"),
    ("running", "succeeded"),
    ("running", "failed"),
    ("running", "cancelled"),
    ("succeeded", "in_review"),
    ("succeeded", "written_back"),
    ("failed", "queued"),
    ("in_review", "approved"),
    ("in_review", "rejected"),
    ("rejected", "queued"),
    ("approved", "written_back"),
}


def test_edge_table_matches_the_contract():
    assert set(iter_legal_edges()) == EXPECTED_EDGES
    assert len(EXPECTED_EDGES) == 12
    assert LEGAL_EDGE_COUNT == 12
    assert set(ALLOWED_TRANSITIONS) == set(TASK_STATUSES)


@pytest.mark.parametrize("from_status,to_status", sorted(EXPECTED_EDGES))
def test_every_legal_edge_is_applied(from_status: str, to_status: str):
    task = status_task(from_status)

    assert can_transition(from_status, to_status) is True
    transition(task, to_status)

    assert str(task.status) == to_status


def test_all_illegal_edges_raise_invalid_transition():
    """Every pair outside the table must raise; this covers AC-2's five."""
    illegal_edges = [
        (source, target)
        for source, target in product(TASK_STATUSES, TASK_STATUSES)
        if (source, target) not in EXPECTED_EDGES
    ]

    # 9 x 9 pairs minus the 12 legal edges, one case per pair.
    assert len(illegal_edges) == 69

    for from_status, target in illegal_edges:
        task = status_task(from_status)
        with pytest.raises(InvalidTransition) as excinfo:
            transition(task, target)
        assert excinfo.value.from_status == from_status
        assert excinfo.value.to_status == target
        # A rejected move must not mutate the task.
        assert str(task.status) == from_status


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        ("queued", "approved"),
        ("queued", "written_back"),
        ("running", "in_review"),
        ("succeeded", "approved"),
        ("failed", "succeeded"),
        ("in_review", "written_back"),
        ("approved", "queued"),
        ("cancelled", "queued"),
        ("written_back", "approved"),
    ],
)
def test_representative_illegal_edges_raise_invalid_transition(from_status, to_status):
    """AC-2 asks for at least five explicit illegal-edge cases."""

    task = status_task(from_status)

    with pytest.raises(InvalidTransition) as excinfo:
        transition(task, to_status)

    assert excinfo.value.from_status == from_status
    assert excinfo.value.to_status == to_status
    assert str(task.status) == from_status


@pytest.mark.parametrize("terminal", sorted(TERMINAL_STATUSES))
def test_terminal_statuses_have_no_outgoing_edge(terminal: str):
    assert allowed_next(terminal) == frozenset()

    for target in TASK_STATUSES:
        task = status_task(terminal)
        with pytest.raises(InvalidTransition):
            transition(task, target)


def test_self_transition_is_illegal():
    for status in TASK_STATUSES:
        task = status_task(status)
        with pytest.raises(InvalidTransition):
            transition(task, status)


def test_direct_orm_assignment_is_guarded_by_the_same_edge_table():
    """A service that bypasses ``transition`` still cannot persist an illegal edge."""

    task = status_task("queued")

    with pytest.raises(InvalidTransition):
        task.status = "approved"
    assert str(task.status) == "queued"

    task.status = "running"
    assert str(task.status) == "running"


def test_unknown_status_is_rejected():
    with pytest.raises(InvalidTransition):
        allowed_next("archived")

    assert can_transition("queued", "archived") is False
    assert can_transition("archived", "queued") is False

    with pytest.raises(InvalidTransition):
        assert_transition("queued", "archived")


def test_assert_transition_reports_task_id():
    with pytest.raises(InvalidTransition) as excinfo:
        assert_transition("queued", "approved", task_id="task-1")

    assert "task-1" in str(excinfo.value)
    assert excinfo.value.task_id == "task-1"


def test_can_transition_matches_edge_table_for_every_pair():
    for source, target in product(TASK_STATUSES, TASK_STATUSES):
        assert can_transition(source, target) is ((source, target) in EXPECTED_EDGES)


def test_allowed_next_lists_only_defined_targets():
    assert allowed_next(TaskStatus.QUEUED) == frozenset({"running", "cancelled"})
    assert allowed_next("running") == frozenset({"succeeded", "failed", "cancelled"})
    assert allowed_next("succeeded") == frozenset({"in_review", "written_back"})
    assert allowed_next("failed") == frozenset({"queued"})
    assert allowed_next("in_review") == frozenset({"approved", "rejected"})
    assert allowed_next("rejected") == frozenset({"queued"})
    assert allowed_next("approved") == frozenset({"written_back"})


def test_transition_can_stamp_updated_at():
    from datetime import datetime, timezone

    at = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    task = status_task("queued")

    transition(task, "running", at=at)

    assert task.updated_at == at


def test_reachable_statuses_are_forward_only():
    assert reachable_statuses("queued") == frozenset(
        {
            "queued",
            "running",
            "succeeded",
            "failed",
            "in_review",
            "approved",
            "rejected",
            "written_back",
            "cancelled",
        }
    )
    # A terminal status cannot reach anything else.
    assert reachable_statuses("written_back") == frozenset({"written_back"})
    assert reachable_statuses("cancelled") == frozenset({"cancelled"})
