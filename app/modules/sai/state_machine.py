"""Status machine for ``sai_task``.

The legal edges are data, not scattered ``if`` statements.  Every caller that
changes ``SaiTask.status`` must go through :func:`transition` (or at least
:func:`assert_transition`), so an illegal move fails fast with
:class:`InvalidTransition` instead of silently persisting an inconsistent task.

Legal edges (12)::

    queued     -> running | cancelled
    running    -> succeeded | failed | cancelled
    succeeded  -> in_review | written_back
    failed     -> queued                 # retry
    in_review  -> approved | rejected
    rejected   -> queued                 # rework after rejection
    approved   -> written_back

``written_back`` and ``cancelled`` are terminal: no edge leaves them.

The database rejects out-of-domain status values through the ``sai_task_status``
enum; the edge rules themselves are application-level because PostgreSQL CHECK
constraints cannot express a transition matrix cleanly.  Workers, the review
queue and the write-back service all share this single table, so the rule lives
in one place.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, Iterable

from app.modules.sai.enums import TASK_STATUSES, TaskStatus

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a model import cycle
    from app.modules.sai.models.sai_task import SaiTask


class InvalidTransition(ValueError):
    """Raised when a task is asked to move along an edge that is not defined."""

    def __init__(
        self,
        from_status: str,
        to_status: str,
        task_id: object | None = None,
    ) -> None:
        self.from_status = str(from_status)
        self.to_status = str(to_status)
        self.task_id = task_id
        message = f"Illegal task status transition: {self.from_status!r} -> {self.to_status!r}"
        if task_id is not None:
            message += f" (task_id={task_id})"
        super().__init__(message)


_EDGES: dict[str, frozenset[str]] = {
    TaskStatus.QUEUED.value: frozenset(
        {TaskStatus.RUNNING.value, TaskStatus.CANCELLED.value}
    ),
    TaskStatus.RUNNING.value: frozenset(
        {
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED.value,
        }
    ),
    TaskStatus.SUCCEEDED.value: frozenset(
        {TaskStatus.IN_REVIEW.value, TaskStatus.WRITTEN_BACK.value}
    ),
    TaskStatus.FAILED.value: frozenset({TaskStatus.QUEUED.value}),
    TaskStatus.IN_REVIEW.value: frozenset(
        {TaskStatus.APPROVED.value, TaskStatus.REJECTED.value}
    ),
    TaskStatus.REJECTED.value: frozenset({TaskStatus.QUEUED.value}),
    TaskStatus.APPROVED.value: frozenset({TaskStatus.WRITTEN_BACK.value}),
    TaskStatus.WRITTEN_BACK.value: frozenset(),
    TaskStatus.CANCELLED.value: frozenset(),
}

#: Read-only view of the edge table; keys are every status, including terminals.
ALLOWED_TRANSITIONS = MappingProxyType(_EDGES)

#: Statuses with no outgoing edge.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {TaskStatus.WRITTEN_BACK.value, TaskStatus.CANCELLED.value}
)

#: Total number of legal directed edges; asserted by the test suite.
LEGAL_EDGE_COUNT: int = sum(len(targets) for targets in ALLOWED_TRANSITIONS.values())


def _status_value(status: str | TaskStatus) -> str:
    """Return the database value of a status, rejecting unknown values."""

    value = status.value if isinstance(status, TaskStatus) else str(status)
    if value not in ALLOWED_TRANSITIONS:
        raise InvalidTransition(value, value)
    return value


def allowed_next(status: str | TaskStatus) -> frozenset[str]:
    """Return the set of statuses reachable from ``status`` in one step."""

    return ALLOWED_TRANSITIONS[_status_value(status)]


def can_transition(from_status: str | TaskStatus, to_status: str | TaskStatus) -> bool:
    """Return True only for an edge present in :data:`ALLOWED_TRANSITIONS`."""

    source = str(from_status.value if isinstance(from_status, TaskStatus) else from_status)
    target = str(to_status.value if isinstance(to_status, TaskStatus) else to_status)
    return target in ALLOWED_TRANSITIONS.get(source, frozenset())


def assert_transition(
    from_status: str | TaskStatus,
    to_status: str | TaskStatus,
    *,
    task_id: object | None = None,
) -> None:
    """Raise :class:`InvalidTransition` unless the edge is defined."""

    if not can_transition(from_status, to_status):
        raise InvalidTransition(
            from_status.value if isinstance(from_status, TaskStatus) else from_status,
            to_status.value if isinstance(to_status, TaskStatus) else to_status,
            task_id=task_id,
        )


def transition(
    task: "SaiTask",
    to_status: str | TaskStatus,
    *,
    at=None,
) -> "SaiTask":
    """Validate and apply one edge on ``task``, returning the same instance.

    The caller keeps control of the transaction; this helper does not commit.
    When ``at`` is provided it is written to ``updated_at`` so a transition
    performed in a batch carries its own business timestamp.
    """

    assert_transition(task.status, to_status, task_id=task.id)
    task.status = to_status  # type: ignore[assignment]
    if at is not None:
        task.updated_at = at
    return task


def reachable_statuses(start: str | TaskStatus) -> frozenset[str]:
    """Return every status reachable from ``start`` over zero or more edges."""

    seen: set[str] = set()
    pending: list[str] = [_status_value(start)]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(ALLOWED_TRANSITIONS[current] - seen)
    return frozenset(seen)


def iter_legal_edges() -> Iterable[tuple[str, str]]:
    """Yield every legal ``(from, to)`` pair in a stable order."""

    for source in TASK_STATUSES:
        for target in sorted(ALLOWED_TRANSITIONS[source]):
            yield source, target
