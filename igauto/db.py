"""SQLite storage for insights history and processed comments."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS daily_account (
    day            TEXT PRIMARY KEY,      -- YYYY-MM-DD (UTC)
    followers      INTEGER,               -- follower_count snapshot / delta as reported
    follows        INTEGER,
    unfollows      INTEGER,
    reach          INTEGER,
    views          INTEGER,
    profile_views  INTEGER,
    accounts_engaged INTEGER,
    fetched_at     TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media (
    media_id       TEXT PRIMARY KEY,
    posted_at      TEXT,
    product_type   TEXT,
    caption        TEXT,
    permalink      TEXT
);

CREATE TABLE IF NOT EXISTS media_insights (
    media_id       TEXT,
    fetched_day    TEXT,
    views          INTEGER,
    reach          INTEGER,
    likes          INTEGER,
    comments       INTEGER,
    shares         INTEGER,
    saved          INTEGER,
    follows        INTEGER,
    profile_visits INTEGER,
    PRIMARY KEY (media_id, fetched_day)
);

CREATE TABLE IF NOT EXISTS processed_comments (
    comment_id     TEXT PRIMARY KEY,
    media_id       TEXT,
    user_id        TEXT,
    username       TEXT,
    keyword        TEXT,
    status         TEXT,                  -- sent | failed | skipped
    detail         TEXT,
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, table: str, row: dict, keys: tuple[str, ...]) -> None:
    """Insert or merge non-null columns into an existing row."""
    cols = list(row)
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(
        f"{c}=COALESCE(excluded.{c}, {table}.{c})" for c in cols if c not in keys
    )
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders}) ON CONFLICT({','.join(keys)})"
    sql += f" DO UPDATE SET {updates}" if updates else " DO NOTHING"
    conn.execute(sql, [row[c] for c in cols])
