import sqlite3
import os
import json

DB_PATH = "/root/crisis-monitor/backend/data/crisis.db"


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
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
            completed_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_indicators_category ON indicators(category);
        CREATE INDEX IF NOT EXISTS idx_history_name_time ON indicator_history(indicator_name, recorded_at);
        CREATE INDEX IF NOT EXISTS idx_dot_analyses_time ON dot_analyses(analyzed_at);
        CREATE INDEX IF NOT EXISTS idx_reports_date ON daily_reports(date);
        CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(triggered_at);
    """)
    # Migration: add briefing column to existing daily_reports tables
    try:
        conn.execute("ALTER TABLE daily_reports ADD COLUMN briefing TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Migration: add narrative column to indicator_history
    try:
        conn.execute("ALTER TABLE indicator_history ADD COLUMN narrative TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Migration: add display_name, category, unit, trigger_level columns to indicator_history
    for col, col_type in [("display_name", "TEXT DEFAULT ''"), ("category", "TEXT DEFAULT ''"),
                           ("unit", "TEXT DEFAULT ''"), ("trigger_level", "TEXT DEFAULT ''")]:
        try:
            conn.execute(f"ALTER TABLE indicator_history ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # column already exists
    # Migration: add name + description columns to pathway_status
    try:
        conn.execute("ALTER TABLE pathway_status ADD COLUMN name TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    try:
        conn.execute("ALTER TABLE indicator_history ADD COLUMN narrative TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # column already exists
    # Migration: add sources column to dot_analyses
    try:
        conn.execute("ALTER TABLE dot_analyses ADD COLUMN sources TEXT DEFAULT '[]'")
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.commit()
    conn.close()
