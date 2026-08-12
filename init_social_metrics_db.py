#!/usr/bin/env python3
import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS platform (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS account (
    id           INTEGER PRIMARY KEY,
    platform_id  INTEGER NOT NULL REFERENCES platform(id),
    handle       TEXT NOT NULL,
    display_name TEXT,
    UNIQUE (platform_id, handle)
);

CREATE TABLE IF NOT EXISTS content (
    id                   INTEGER PRIMARY KEY,
    platform_id          INTEGER NOT NULL REFERENCES platform(id),
    account_id           INTEGER NOT NULL REFERENCES account(id),

    platform_content_id  TEXT,
    url                  TEXT,

    is_post              INTEGER NOT NULL DEFAULT 1,
    content_type         TEXT NOT NULL DEFAULT 'post',
    title                TEXT,
    body                 TEXT,

    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes                TEXT,
    engagement_time      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    link                 TEXT,

    UNIQUE (platform_id, platform_content_id)
);

CREATE TABLE IF NOT EXISTS engagement_snapshot (
    id                   INTEGER PRIMARY KEY,
    content_id           INTEGER NOT NULL REFERENCES content(id),
    snapshot_ts          TEXT NOT NULL,

    impressions          INTEGER,
    views                INTEGER,
    likes                INTEGER,
    comments             INTEGER,
    shares               INTEGER,
    saves                INTEGER,
    clicks               INTEGER,
    watch_time_seconds   INTEGER,

    UNIQUE (content_id, snapshot_ts)
);

CREATE VIEW IF NOT EXISTS latest_engagement AS
SELECT
    c.id             AS content_id,
    c.platform_id,
    c.account_id,
    c.is_post,
    c.content_type,
    c.title,
    c.url,
    c.created_at,
    c.notes,
    c.engagement_time,
    c.link,
    e.snapshot_ts,
    e.impressions,
    e.views,
    e.likes,
    e.comments,
    e.shares,
    e.saves,
    e.clicks,
    e.watch_time_seconds
FROM content c
JOIN engagement_snapshot e
  ON e.content_id = c.id
JOIN (
    SELECT content_id, MAX(snapshot_ts) AS max_ts
    FROM engagement_snapshot
    GROUP BY content_id
) latest
  ON latest.content_id = e.content_id
 AND latest.max_ts = e.snapshot_ts;
"""


def init_db(path: str = "social_metrics.db") -> None:
    db_path = Path(path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    print(f"Initialized database at {db_path.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Initialize social media metrics SQLite database."
    )
    parser.add_argument(
        "--db-path",
        default="social_metrics.db",
        help="Path to SQLite database file (default: social_metrics.db)",
    )
    args = parser.parse_args()
    init_db(args.db_path)
