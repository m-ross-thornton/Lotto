"""
Create (or migrate) the SQLite schema.

Run with:
    uv run python -m db.schema
"""

from db import get_connection

DDL = """
CREATE TABLE IF NOT EXISTS games (
    game_id           TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    price             REAL NOT NULL,
    top_prize         REAL,
    probability_denom REAL,       -- "1 in X" denominator (fixed for the print run)
    launch_date       DATE,
    est_total_tickets INTEGER,    -- derived: sum(start_counts) × probability_denom
    first_seen_at     DATETIME NOT NULL,
    last_scraped_at   DATETIME NOT NULL,
    is_active         BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS snapshots (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id               TEXT NOT NULL REFERENCES games(game_id),
    scraped_at            DATETIME NOT NULL,
    top_prizes_remaining  INTEGER NOT NULL,
    all_prizes_remaining  INTEGER NOT NULL,
    est_remaining_tickets INTEGER NOT NULL,
    ev_per_dollar         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS prize_tiers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
    game_id         TEXT NOT NULL REFERENCES games(game_id),
    prize_value     REAL NOT NULL,
    start_count     INTEGER NOT NULL,
    remaining_count INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_game_time
    ON snapshots(game_id, scraped_at DESC);

CREATE INDEX IF NOT EXISTS idx_prize_tiers_snapshot
    ON prize_tiers(snapshot_id);
"""


def init_db():
    with get_connection() as conn:
        conn.executescript(DDL)
    print("Schema initialised (or already up to date).")


if __name__ == "__main__":
    init_db()
