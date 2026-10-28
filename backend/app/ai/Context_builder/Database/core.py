"""Create a single Database instance for the whole package."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.Context_builder.types import ensure_utc
from app.ai.Context_builder.database.incident_queries import IncidentQueries
from app.ai.Context_builder.database.site_queries import SiteQueries
from app.ai.Context_builder.database.alert_queries import AlertQueries


class Database(IncidentQueries, SiteQueries, AlertQueries):
    """Universal DB access object. USes the session from app.database and
    hands out one short session per function

    The mixins call self.session() and self._utc(); they hold no state.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from app.database import SessionLocal  # lazy: keeps tests free to inject
            session_factory = SessionLocal
        self._session_factory = session_factory

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session; commit on success, rollback on error, always closes."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> bool:
        """Cheap connectivity check (SELECT 1). Never raises."""
        try:
            with self.session() as s:
                s.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    @staticmethod
    def _utc(dt: datetime | None) -> datetime | None:
        """Naive -> aware UTC (SQLite returns naive); aware -> converted to UTC."""
        return ensure_utc(dt)


_instance: Database | None = None
_lock = threading.Lock()


def get_database() -> Database:
    """Lazy, thread-safe singleton accessor."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = Database()
    return _instance


def reset_database(db: Database | None = None) -> None:
    """Tests only: replace (or clear) the singleton, like with an in-memory SQLite db."""
    global _instance
    with _lock:
        _instance = db