"""Shared pytest fixtures.

The suite runs against a real PostgreSQL 16 database because the delivery relies
on PostgreSQL-native enum types, JSONB, partial unique indexes and a composite
foreign key.  ``TEST_DATABASE_URL`` is mandatory and the database name must
contain ``test``; the fixture drops and recreates the ``public`` schema, so it
must never point at a shared database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app import modules  # noqa: F401,E402  (register package)
from app.modules.sai import models  # noqa: F401,E402  (register both tables)
from app.db import Base  # noqa: F401,E402

TABLES_IN_TRUNCATE_ORDER = ("sai_output", "sai_task")


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.exit(
            "TEST_DATABASE_URL is required, e.g. "
            "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME_WITH_TEST",
            returncode=2,
        )

    parsed = make_url(url)
    database = (parsed.database or "").lower()
    if "test" not in database:
        pytest.exit(
            f"Refusing to run destructive test fixtures against non-test database "
            f"{parsed.database!r}. The database name must contain 'test'.",
            returncode=2,
        )
    return url


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def engine(database_url: str, alembic_config: Config):
    """Reset the public schema once, then apply the Alembic migration."""

    eng = create_engine(database_url, poolclass=NullPool, future=True)
    with eng.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.commit()

    command.upgrade(alembic_config, "head")

    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """A session with empty delivery tables before and after each test."""

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.rollback()
        db_session.close()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE TABLE "
                    + ", ".join(TABLES_IN_TRUNCATE_ORDER)
                    + " RESTART IDENTITY CASCADE"
                )
            )
