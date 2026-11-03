"""
Creates an empty SQLite test database in ./data using the REAL app models.
Run:  python init_db.py (Resets the database and puts it back in data/context_test.db)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Assumes this file lives in backend/context_test/. Adjust parents[1] if you move it.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.ai.Context_builder.database.core import Database

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "context_test.db"

# Only the tables the context package needs.
TEST_MODELS = [
    models.SiteProfile,
    models.Sensor,
    models.Event,
    models.Alert,
    models.Incident,
    models.ExplanationLog,
]


def make_engine(db_path: Path = DB_PATH, reset: bool = False) -> Engine:
    """SQLite engine on a file in ./data. reset=True deletes the old file first
    (on Windows, close any other process using it before resetting)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if reset and db_path.exists():
        db_path.unlink()

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


def create_tables(engine: Engine) -> None:
    """Create the test tables."""
    models.Base.metadata.create_all(
        engine, tables=[m.__table__ for m in TEST_MODELS]
    )


def make_database(engine: Engine) -> Database:
    """A Database instance (the one the package uses) bound to this engine."""
    return Database(session_factory=sessionmaker(bind=engine, expire_on_commit=False))

if __name__ == "__main__":
    eng = make_engine(reset=True)
    create_tables(eng)
    print(f"Created {DB_PATH}")
    for m in TEST_MODELS:
        print("  table:", m.__tablename__)