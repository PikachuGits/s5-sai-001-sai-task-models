"""Deterministic input hashing for ``sai_task`` idempotency.

The unique index on ``(org_id, task_type, subject_id, input_hash)`` only works
if two runs over the same meaningful input produce the same digest.  Callers
therefore hash a *whitelisted*, canonical representation instead of a raw
request body: transport fields such as request ids, timestamps or trace
headers must not turn a retry into a new task.

Canonical form: JSON with sorted keys, compact separators and UTF-8 text.
``fields`` selects the business fields that participate; a missing field and an
explicit ``null`` hash the same, which is intentional.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def canonical_input(
    payload: Mapping[str, Any],
    *,
    fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return the normalised mapping that is fed to the hash.

    Only ``fields`` participate when given; every omitted key is ignored even
    if present in ``payload``.  Values that are not JSON-native are rendered by
    ``json.dumps(default=str)`` so a date or UUID still produces a stable digest.
    """

    if fields is None:
        selected = dict(payload)
    else:
        selected = {field: payload.get(field) for field in fields}
    # Round-trip through JSON to normalise nested tuples/sets/dates consistently.
    return json.loads(
        json.dumps(selected, sort_keys=True, separators=(",", ":"), default=str)
    )


def compute_input_hash(
    payload: Mapping[str, Any],
    *,
    fields: Iterable[str] | None = None,
) -> str:
    """Return a lower-case SHA-256 hex digest of the canonical input."""

    canonical = json.dumps(
        canonical_input(payload, fields=fields),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest


def is_valid_input_hash(value: str) -> bool:
    """Return True when ``value`` is a lower-case SHA-256 hex digest."""

    return bool(_SHA256_HEX.match(value))
