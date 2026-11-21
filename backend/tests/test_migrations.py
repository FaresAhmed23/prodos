"""The migration is the schema (F-9).

`create_all` could only ever create missing tables, so a column added to a model
silently did nothing to an existing database. These tests are the guard against
that class of change reappearing: they prove the checked-in migration produces
exactly the schema the models describe, and that it reverses.
"""

from pathlib import Path

import logging

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.config import settings
from app.database import Base
import app.models  # noqa: F401  -- registers the tables
import app.admin  # noqa: F401  -- logger must exist before alembic can disable it

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "frames", "events", "alerts", "explanation_logs", "sensors",
    "site_profile", "incidents", "score_snapshots", "checklist_answers",
}


def alembic_config() -> Config:
    """Same absolute-path construction app.main.run_migrations uses."""
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_ROOT))
    return cfg


@pytest.fixture
def migrated(tmp_path, monkeypatch):
    """A database built by the migration, not by create_all."""
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(alembic_config(), "head")
    return url


def tables_in(url: str) -> set[str]:
    names = set(inspect(create_engine(url)).get_table_names())
    return {n for n in names if not n.startswith("sqlite_") and n != "alembic_version"}


# --- the migration produces the schema the models describe -----------------


def test_upgrade_creates_every_table(migrated):
    assert tables_in(migrated) == TABLES


def test_migration_matches_the_models_with_no_drift(migrated):
    """The check that matters.

    A non-empty diff means someone edited a model and did not write the matching
    revision. Under create_all that was invisible; here it fails the build.
    """
    engine = create_engine(migrated)
    with engine.connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "render_as_batch": True}
        )
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], f"models have drifted from the migration: {diff}"


def test_migration_builds_the_same_schema_as_create_all(tmp_path, monkeypatch):
    """Direct structural comparison, not just model agreement.

    `compare_metadata` normalises some things away. This builds the schema both
    ways and compares tables, columns, types, nullability, PKs and indexes.
    """
    mig_url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", mig_url)
    command.upgrade(alembic_config(), "head")

    crt_url = f"sqlite:///{(tmp_path / 'c.db').as_posix()}"
    Base.metadata.create_all(create_engine(crt_url))

    def snapshot(url):
        insp = inspect(create_engine(url))
        out = {}
        for table in sorted(insp.get_table_names()):
            if table.startswith("sqlite_") or table == "alembic_version":
                continue
            out[table] = (
                {c["name"]: (str(c["type"]), bool(c["nullable"])) for c in insp.get_columns(table)},
                tuple(insp.get_pk_constraint(table)["constrained_columns"]),
                tuple(sorted((i["name"], tuple(i["column_names"])) for i in insp.get_indexes(table))),
            )
        return out

    assert snapshot(mig_url) == snapshot(crt_url)


def test_autoincrement_variant_survives_the_migration(tmp_path, monkeypatch):
    """frames.id is BigInteger with an Integer fallback for SQLite.

    If a revision hardcoded BIGINT the SQLite dev/test path would stop
    autoincrementing and every frame insert outside Postgres would fail.
    """
    url = f"sqlite:///{(tmp_path / 'v.db').as_posix()}"
    monkeypatch.setattr(settings, "database_url", url)
    command.upgrade(alembic_config(), "head")
    cols = {c["name"]: str(c["type"]) for c in inspect(create_engine(url)).get_columns("frames")}
    assert "BIGINT" not in cols["id"].upper()
    assert cols["id"].upper().startswith("INTEGER")


def test_every_index_is_created(migrated):
    insp = inspect(create_engine(migrated))
    expected = {
        "frames": {"ix_frames_sensor_id", "ix_frames_received_at", "ix_frames_frame_type", "ix_frames_src_mac", "ix_frames_bssid"},
        "events": {"ix_events_event_type", "ix_events_detected_at"},
        "alerts": {"ix_alerts_event_id", "ix_alerts_created_at", "ix_alerts_status"},
        "explanation_logs": {"ix_explanation_logs_provider_used", "ix_explanation_logs_created_at"},
        "sensors": {"ix_sensors_status"},
        "site_profile": set(),
        "incidents": {"ix_incidents_site_key_last"},
        "score_snapshots": {"ix_score_snapshots_site_id_computed_at"},
        "checklist_answers": set(),
    }
    for table, names in expected.items():
        got = {i["name"] for i in insp.get_indexes(table)}
        assert names <= got, f"{table} missing {names - got}"


def test_site_profile_trust_token_schema(migrated):
    """F-21 §3: three nullable token columns plus the unique constraint.

    `compare_metadata` does not reliably compare unique constraints, so this
    inspects the built schema directly. The unique constraint is what keeps
    token lookup unambiguous; NULL (not enrolled) stays unconstrained.
    """
    insp = inspect(create_engine(migrated))
    cols = {
        c["name"]: (str(c["type"]), bool(c["nullable"]))
        for c in insp.get_columns("site_profile")
    }
    assert cols["trust_token"] == ("VARCHAR(64)", True)
    assert cols["trust_token_created_at"] == ("DATETIME", True)
    assert cols["trust_token_rotated_at"] == ("DATETIME", True)
    unique = {
        u["name"]: tuple(u["column_names"])
        for u in insp.get_unique_constraints("site_profile")
    }
    assert unique["uq_site_profile_trust_token"] == ("trust_token",)


# --- reversibility ---------------------------------------------------------


def test_downgrade_removes_everything(migrated):
    command.downgrade(alembic_config(), "base")
    assert tables_in(migrated) == set()


def test_upgrade_downgrade_upgrade_round_trips(migrated):
    command.downgrade(alembic_config(), "base")
    command.upgrade(alembic_config(), "head")
    assert tables_in(migrated) == TABLES


def test_upgrade_is_idempotent(migrated):
    """The app runs this on every boot; a second run must be a no-op, not an error."""
    command.upgrade(alembic_config(), "head")
    command.upgrade(alembic_config(), "head")
    assert tables_in(migrated) == TABLES


def test_migrations_keep_the_app_loggers_enabled(migrated):
    """Alembic's fileConfig default disables every existing logger.

    The lifespan imports the app loggers before running migrations, so the
    default silently killed all backend logging after startup.
    """
    assert not logging.getLogger("app.admin").disabled


# --- the migration chain itself --------------------------------------------


def test_exactly_one_head():
    scripts = ScriptDirectory.from_config(alembic_config())
    heads = scripts.get_heads()
    assert len(heads) == 1, f"expected a single head, got {heads}"


def test_base_revision_has_no_parent():
    """It must be the base revision: the pilot databases predate Alembic.

    `walk_revisions()` yields head first, so the base is the last one.
    """
    scripts = ScriptDirectory.from_config(alembic_config())
    revision = list(scripts.walk_revisions())[-1]
    assert revision.down_revision is None


def test_version_is_stamped(migrated):
    engine = create_engine(migrated)
    with engine.connect() as conn:
        stamped = conn.exec_driver_sql("select version_num from alembic_version").scalar()
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert stamped == head
