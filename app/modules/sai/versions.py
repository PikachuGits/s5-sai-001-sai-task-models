"""Output version allocation for ``sai_output``.

``version`` starts at 1 for the first model output and increases by exactly one
for every human edit.  The helper is pure so it is trivially testable; the
partial unique index ``uq_sai_output_task_version`` is the concurrency guard:
if two editors race, one insert fails and the caller retries with the next
version instead of overwriting history.
"""

from __future__ import annotations

from typing import Iterable


def next_output_version(existing_versions: Iterable[int]) -> int:
    """Return ``max(existing) + 1``, or 1 when the task has no output yet."""

    versions = [int(version) for version in existing_versions]
    return max(versions, default=0) + 1
