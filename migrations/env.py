"""Alembic environment for the 招商 AI tables.

``DATABASE_URL`` is the only accepted source of the connection string so the
migration cannot silently target a developer's default database.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db import Base
from app import modules  # noqa: F401  (registers app.modules.sai models)
from app.modules.sai import models  # noqa: F401  (explicit model registration)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _require_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required, e.g. "
            "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME"
        )
    return url


def run_migrations_offline() -> None:
    url = _require_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _require_url()
    # Alembic treats ``%`` in ini values as interpolation; escape it.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
