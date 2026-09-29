"""SQLite storage in the gitignored data directory (spec section 7).

WAL mode and a busy timeout let the API server and the CLI share the file.
Times are stored as UTC ISO-8601 strings.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_responses (
    request_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    engine TEXT NOT NULL,
    params TEXT NOT NULL,
    body TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    search_id TEXT,
    status TEXT NOT NULL,              -- ok | empty | error
    PRIMARY KEY (request_key, version)
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    engine TEXT NOT NULL,
    request_key TEXT NOT NULL,
    search_id TEXT,
    analysis_id TEXT,
    status TEXT NOT NULL               -- ok | empty | error (only ok/empty are billed)
);
CREATE INDEX IF NOT EXISTS ledger_time ON ledger (timestamp);

CREATE TABLE IF NOT EXISTS places (
    place_key TEXT PRIMARY KEY,
    data_id TEXT,
    place_id TEXT,
    title TEXT,
    address TEXT,
    area TEXT,
    lat REAL,
    lng REAL,
    type TEXT,
    type_group TEXT,
    rating REAL,
    total_reviews INTEGER
);

CREATE TABLE IF NOT EXISTS target_reviews (
    review_id TEXT PRIMARY KEY,
    place_key TEXT NOT NULL,
    contributor_id TEXT,
    rating INTEGER,
    iso_date TEXT,
    edited_at TEXT,
    text_original TEXT,
    text_length INTEGER,
    text_script TEXT,
    has_images INTEGER,
    reviewer_total_reviews INTEGER,    -- NULL = unknown, never 0 by default
    reviewer_total_photos INTEGER,
    local_guide INTEGER
);
CREATE INDEX IF NOT EXISTS target_reviews_place ON target_reviews (place_key);

CREATE TABLE IF NOT EXISTS contributors (
    contributor_id TEXT PRIMARY KEY,
    name TEXT,
    level INTEGER,
    points INTEGER,
    local_guide INTEGER,
    contributions TEXT,                -- JSON object of counts
    reviews_returned INTEGER,
    history_truncated INTEGER,
    fetch_status TEXT,                 -- ok | empty | private | error
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS contributor_reviews (
    contributor_id TEXT NOT NULL,
    review_id TEXT NOT NULL,
    place_key TEXT,
    rating INTEGER,
    relative_date TEXT,
    date_min TEXT,                     -- IST calendar date
    date_max TEXT,
    date_precision_days INTEGER,
    edited INTEGER,
    image_dates TEXT,                  -- JSON list of YYYY-MM-DD
    text_original TEXT,
    text_length INTEGER,
    fetched_at TEXT,
    PRIMARY KEY (contributor_id, review_id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    input TEXT NOT NULL,
    place_key TEXT,
    params TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,              -- queued | running | paused | done | cancelled | error
    stage TEXT,
    searches_used INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    finished_at TEXT,
    algorithm_version TEXT,
    report TEXT,
    state TEXT,                        -- JSON: resolved place, expansion plan, pause info
    error TEXT
);

CREATE TABLE IF NOT EXISTS llm_responses (
    request_key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input TEXT NOT NULL,
    output TEXT NOT NULL,
    validated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""

_init_lock = threading.Lock()
_initialized: set[str] = set()


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def default_path() -> Path:
    return config.data_dir() / "reviewring.sqlite3"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open a connection (one per thread) and make sure the schema exists."""
    path = str(path or default_path())
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    with _init_lock:
        if path not in _initialized:
            conn.executescript(SCHEMA)
            _migrate(conn)
            _initialized.add(path)
    return conn


# Columns added after a table first shipped: (table, column, type).
_ADDED_COLUMNS = [("analyses", "state", "TEXT"), ("analyses", "error", "TEXT")]


def _migrate(conn: sqlite3.Connection) -> None:
    for table, column, kind in _ADDED_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
