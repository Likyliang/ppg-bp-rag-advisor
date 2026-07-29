from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.services.config_loader import PROJECT_ROOT


class Base(DeclarativeBase):
    pass


_LOCK = threading.RLock()
_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker] = None
_ENGINE_URL: Optional[str] = None
_SCHEMA_READY_URL: Optional[str] = None


def _database_url() -> str:
    raw = os.getenv("ADMIN_DATABASE_URL", "sqlite:///var/admin.db").strip()
    if raw.startswith("sqlite:///") and not raw.startswith("sqlite:////"):
        relative = raw[len("sqlite:///") :]
        path = Path(relative)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        return f"sqlite:///{path}"
    return raw


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine() -> Engine:
    global _ENGINE, _SESSION_FACTORY, _ENGINE_URL
    url = _database_url()
    with _LOCK:
        if _ENGINE is not None and _ENGINE_URL == url:
            return _ENGINE
        if _ENGINE is not None:
            _ENGINE.dispose()
        kwargs = {"future": True, "pool_pre_ping": True}
        if url.startswith("sqlite:"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _ENGINE = create_engine(url, **kwargs)
        if url.startswith("sqlite:"):
            event.listen(_ENGINE, "connect", _configure_sqlite)
        _SESSION_FACTORY = sessionmaker(bind=_ENGINE, expire_on_commit=False, future=True)
        _ENGINE_URL = url
        return _ENGINE


def init_admin_db() -> None:
    global _SCHEMA_READY_URL
    # Import models before create_all so every table is registered.
    from app.admin import models  # noqa: F401

    engine = get_engine()
    with _LOCK:
        if _SCHEMA_READY_URL == _ENGINE_URL:
            return
        Base.metadata.create_all(engine)
        _apply_additive_schema_updates(engine)
        if engine.dialect.name == "sqlite" and engine.url.database:
            try:
                os.chmod(engine.url.database, 0o600)
            except OSError:
                pass
        _SCHEMA_READY_URL = _ENGINE_URL


def _apply_additive_schema_updates(engine: Engine) -> None:
    """Upgrade pre-Alembic V1 databases without deleting local admin state.

    Early V1 development builds used ``create_all`` before the migration files
    existed.  SQLAlchemy does not add columns to existing tables, so keep this
    small, idempotent bridge for those local SQLite databases. Future released
    schema changes belong in Alembic revisions.
    """

    if engine.dialect.name != "sqlite":
        return
    additions = {
        "literature_drafts": {
            "review_note": "TEXT",
            "reviewed_at": "DATETIME",
            "base_catalog_revision": "VARCHAR(64)",
        },
        "admin_jobs": {"process_pid": "INTEGER"},
    }
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in tables:
                continue
            existing = {item["name"] for item in inspector.get_columns(table_name)}
            for column_name, sql_type in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {sql_type}')
                    )
        # Early V1 builds briefly stored correlation/client identifiers in the
        # anonymous metrics table. Rebuild that local table using only the
        # approved anonymous fields; merely blanking the old NOT NULL column
        # would make future ORM inserts fail when it is omitted.
        metric_columns = (
            {item["name"] for item in inspector.get_columns("api_metrics")}
            if "api_metrics" in tables
            else set()
        )
        if {"request_id", "client_id"}.issubset(metric_columns):
            connection.execute(text("DROP TABLE IF EXISTS api_metrics_privacy_migration"))
            connection.execute(
                text(
                    """
                    CREATE TABLE api_metrics_privacy_migration (
                        id VARCHAR(36) NOT NULL PRIMARY KEY,
                        created_at DATETIME NOT NULL,
                        route_name VARCHAR(120) NOT NULL,
                        method VARCHAR(12) NOT NULL,
                        status_code INTEGER NOT NULL,
                        latency_ms FLOAT NOT NULL,
                        generation_mode VARCHAR(120),
                        retrieval_backend VARCHAR(60),
                        safety_fallback BOOLEAN NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO api_metrics_privacy_migration
                    (id, created_at, route_name, method, status_code, latency_ms,
                     generation_mode, retrieval_backend, safety_fallback)
                    SELECT id, created_at, route_name, method, status_code, latency_ms,
                           generation_mode, retrieval_backend, safety_fallback
                    FROM api_metrics
                    """
                )
            )
            connection.execute(text("DROP TABLE api_metrics"))
            connection.execute(text("ALTER TABLE api_metrics_privacy_migration RENAME TO api_metrics"))
            connection.execute(text("CREATE INDEX ix_api_metrics_created_at ON api_metrics (created_at)"))
            connection.execute(text("CREATE INDEX ix_api_metrics_route_name ON api_metrics (route_name)"))
            connection.execute(text("CREATE INDEX ix_api_metrics_status_code ON api_metrics (status_code)"))


def get_db() -> Generator[Session, None, None]:
    init_admin_db()
    assert _SESSION_FACTORY is not None
    db = _SESSION_FACTORY()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    init_admin_db()
    assert _SESSION_FACTORY is not None
    db = _SESSION_FACTORY()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def reset_admin_engine_for_tests() -> None:
    """Drop cached engine bindings after a test changes ADMIN_DATABASE_URL."""

    global _ENGINE, _SESSION_FACTORY, _ENGINE_URL, _SCHEMA_READY_URL
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
        _ENGINE = None
        _SESSION_FACTORY = None
        _ENGINE_URL = None
        _SCHEMA_READY_URL = None
