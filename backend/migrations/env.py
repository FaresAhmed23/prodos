"""Alembic environment.

Two decisions here that are easy to get wrong:

* The database URL comes from `app.config.settings`, never from `alembic.ini`.
  One source of truth means a migration cannot be pointed at a different
  database than the app by editing a stray ini file.

* Postgres is pinned to a UTC session exactly like `app/database.py` does. That
  is not cosmetic: without it a migration run on a Cairo host renders
  TIMESTAMPTZ as +03:00, and the F-4 lesson was that this silently changes the
  JSON the dashboard sees.

`compare_type=True` is what makes `alembic check` able to catch a column type
changing in a model. `render_as_batch` is required for SQLite, which cannot
ALTER most things; SQLite is the default dev/test database here, so without it
the second migration would work in production and fail for everyone else.
"""

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import create_engine, pool

# Make this file self-sufficient about `import app`. Both `alembic` from a shell
# and the programmatic upgrade in app/main.py can run with an arbitrary working
# directory (the Docker image's WORKDIR is /app, but nothing guarantees the
# caller is in it), and a migration that only resolves its own imports from the
# current directory fails in the container while working fine on a laptop.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: E402,F401  -- registers the tables on Base.metadata
from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402

config = context.config
if config.config_file_name is not None:
    # fileConfig defaults to disable_existing_loggers=True, which silences
    # every app.* logger when the lifespan runs migrations after import.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _engine_kwargs() -> dict:
    """Match app.database's Postgres session pinning. See module docstring."""
    if settings.database_url.startswith("postgresql"):
        return {"connect_args": {"options": "-c timezone=UTC"}}
    return {}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (`alembic upgrade --sql`)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # NullPool: a migration should not run against a connection that a previous
    # pooled session left mid-transaction.
    connectable = create_engine(
        settings.database_url, poolclass=pool.NullPool, **_engine_kwargs()
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
