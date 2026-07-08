import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Alembic uses the migration role (DDL privileges).
# Falls back to DATABASE_URL so a single-role local setup still works.
_migration_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not _migration_url:
    raise RuntimeError(
        "Set MIGRATION_DATABASE_URL (or DATABASE_URL) before running Alembic."
    )
_migration_url = re.sub(r"^postgresql(\+psycopg)?://", "postgresql+psycopg2://", _migration_url)
config.set_main_option("sqlalchemy.url", _migration_url)

# Import all models so autogenerate can detect every table.
from db.database import Base  # noqa: E402
import db.models  # noqa: E402, F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
