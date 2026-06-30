import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# ── DB path ───────────────────────────────────────────────────────────────
# Read from env first; fall back to a path relative to this file so the
# project works without any env vars in development.
# File layout: src/db/database.py → parents[2] = backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
DB_PATH: str = os.environ.get(
    "CRISIS_DB_PATH",
    str(_BACKEND_ROOT / "data" / "crisis.db"),
)


def get_db() -> sqlite3.Connection:
    """Return an open SQLite connection with row_factory set to sqlite3.Row.

    Callers are responsible for calling conn.close(). Prefer get_db_ctx()
    for automatic cleanup.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db_ctx() -> Generator[sqlite3.Connection, None, None]:
    """Context manager that opens a connection and guarantees close on exit.

    Usage::

        with get_db_ctx() as conn:
            rows = conn.execute("SELECT ...").fetchall()
    """
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


# ============================================================
# Schema creation
# ============================================================

_CREATE_TABLES = """
    CREATE TABLE IF NOT EXISTS indicators (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        value REAL,
        unit TEXT,
        status TEXT NOT NULL DEFAULT 'normal',
        trigger_level TEXT,
        metadata TEXT,
        fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS indicator_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        indicator_name TEXT NOT NULL,
        display_name TEXT DEFAULT '',
        category TEXT DEFAULT '',
        value REAL,
        unit TEXT DEFAULT '',
        status TEXT NOT NULL,
        trigger_level TEXT DEFAULT '',
        narrative TEXT DEFAULT '',
        data_status TEXT DEFAULT 'live',
        recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS dot_analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dot_number INTEGER NOT NULL,
        dot_name TEXT NOT NULL,
        status TEXT NOT NULL,
        summary TEXT NOT NULL,
        key_signals TEXT,
        sources TEXT DEFAULT '[]',
        tier TEXT DEFAULT 'live',
        analyzed_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS pathway_status (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pathway TEXT NOT NULL,
        name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 0,
        signals TEXT,
        assessed_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS daily_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL UNIQUE,
        dot_summary TEXT NOT NULL,
        pathway_summary TEXT NOT NULL,
        end_state TEXT NOT NULL,
        synthesis TEXT NOT NULL,
        five_questions TEXT NOT NULL,
        confidence TEXT NOT NULL,
        composite_score INTEGER DEFAULT 0,
        briefing TEXT DEFAULT '',
        trigger_source TEXT DEFAULT '',
        dashboard_state TEXT DEFAULT 'ACTIVE',
        category_rss_scores TEXT DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        indicator TEXT NOT NULL,
        message TEXT NOT NULL,
        triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
        acknowledged INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_data TEXT NOT NULL,
        completed_at TEXT NOT NULL DEFAULT (datetime('now')),
        errors TEXT DEFAULT '',
        trigger_source TEXT DEFAULT '',
        overall_tier TEXT DEFAULT 'live'
    );
    CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category);
    CREATE INDEX IF NOT EXISTS idx_history_name_time ON indicator_history(indicator_name, recorded_at);
    CREATE INDEX IF NOT EXISTS idx_dot_analyses_time ON dot_analyses(analyzed_at);
    CREATE INDEX IF NOT EXISTS idx_reports_date ON daily_reports(date);
    CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(triggered_at);
"""


# ============================================================
# Versioned migrations
# ============================================================
# Each entry is (version, sql). Versions are applied in order and tracked
# in the schema_migrations table so each runs exactly once.
# DO NOT reorder or remove entries — only append new ones.

_MIGRATIONS: list[tuple[int, str]] = [
    (1, "ALTER TABLE daily_reports ADD COLUMN briefing TEXT DEFAULT ''"),
    (2, "ALTER TABLE indicator_history ADD COLUMN narrative TEXT DEFAULT ''"),
    (3, "ALTER TABLE indicator_history ADD COLUMN display_name TEXT DEFAULT ''"),
    (4, "ALTER TABLE indicator_history ADD COLUMN category TEXT DEFAULT ''"),
    (5, "ALTER TABLE indicator_history ADD COLUMN unit TEXT DEFAULT ''"),
    (6, "ALTER TABLE indicator_history ADD COLUMN trigger_level TEXT DEFAULT ''"),
    (7, "ALTER TABLE pathway_status ADD COLUMN name TEXT DEFAULT ''"),
    # v8: was previously missing (a duplicate narrative migration was mistakenly
    # applied here instead) — this adds the correct description column.
    (8, "ALTER TABLE pathway_status ADD COLUMN description TEXT DEFAULT ''"),
    (9, "ALTER TABLE dot_analyses ADD COLUMN sources TEXT DEFAULT '[]'"),
    (10, "ALTER TABLE daily_reports ADD COLUMN trigger_source TEXT DEFAULT ''"),
    (11, "ALTER TABLE dot_analyses ADD COLUMN tier TEXT DEFAULT 'live'"),
    (12, "ALTER TABLE pipeline_runs ADD COLUMN errors TEXT DEFAULT ''"),
    (13, "ALTER TABLE pipeline_runs ADD COLUMN trigger_source TEXT DEFAULT ''"),
    (14, "ALTER TABLE pipeline_runs ADD COLUMN overall_tier TEXT DEFAULT 'live'"),
    (15, "ALTER TABLE indicator_history ADD COLUMN data_status TEXT DEFAULT 'live'"),
    (16, "ALTER TABLE daily_reports ADD COLUMN dashboard_state TEXT DEFAULT 'ACTIVE'"),
    (17, "ALTER TABLE daily_reports ADD COLUMN category_rss_scores TEXT DEFAULT '{}'"),
]


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version (0 if none applied)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply any pending migrations in version order."""
    current = _get_schema_version(conn)
    for version, sql in _MIGRATIONS:
        if version <= current:
            continue
        try:
            conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
        except sqlite3.OperationalError:
            # Column already exists (database pre-dates migration tracking).
            # Record the version so we don't retry on next startup.
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                (version,),
            )
    conn.commit()


def init_db() -> None:
    """Create tables (if needed) and apply any pending schema migrations."""
    with get_db_ctx() as conn:
        conn.executescript(_CREATE_TABLES)
        _apply_migrations(conn)
