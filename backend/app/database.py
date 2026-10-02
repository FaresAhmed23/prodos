from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

# Postgres renders TIMESTAMPTZ in whatever TimeZone the session has, so the API
# returned '...+03:00' on this Cairo host and '...Z' on a UTC one -- same stored
# instant, different JSON, which breaks the project's timezone-aware-UTC
# convention and any client that compares strings. Pin the session zone at
# connect time, as a libpq option, so it survives the pool's rollback.
_engine_args = (
    {"connect_args": {"options": "-c timezone=UTC"}}
    if settings.database_url.startswith("postgresql") else {}
)

engine = create_engine(settings.database_url, pool_pre_ping=True, **_engine_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session