"""Declarative base and database URL handling for the SAI persistence layer.

The delivery targets PostgreSQL 16.  The connection string is read from
``DATABASE_URL`` only; there is deliberately no fallback to a developer
machine's default database, so a misconfigured environment fails loudly
instead of migrating the wrong cluster.
"""

from __future__ import annotations

import os

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by ``sai_task`` and ``sai_output``."""

    metadata = MetaData()


def get_database_url() -> str:
    """Return the configured database URL or fail loudly."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required, e.g. "
            "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME"
        )
    return url
