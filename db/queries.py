"""
Named database operations — all writes go through here.
"""

import sqlite3
from datetime import datetime

from scraper.md_lottery import Game


def upsert_game(conn: sqlite3.Connection, game: Game, now: datetime):
    conn.execute(
        """
        INSERT INTO games
            (game_id, name, price, top_prize, probability_denom,
             launch_date, est_total_tickets, first_seen_at, last_scraped_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(game_id) DO UPDATE SET
            name              = excluded.name,
            price             = excluded.price,
            top_prize         = excluded.top_prize,
            probability_denom = excluded.probability_denom,
            launch_date       = excluded.launch_date,
            est_total_tickets = excluded.est_total_tickets,
            last_scraped_at   = excluded.last_scraped_at,
            is_active         = 1
        """,
        (
            game.game_id,
            game.name,
            game.price,
            game.top_prize,
            game.probability_denominator,
            game.launch_date.isoformat() if game.launch_date else None,
            game.estimated_total_tickets,
            now.isoformat(),
            now.isoformat(),
        ),
    )


def insert_snapshot(conn: sqlite3.Connection, game: Game, now: datetime) -> int:
    cur = conn.execute(
        """
        INSERT INTO snapshots
            (game_id, scraped_at, top_prizes_remaining,
             all_prizes_remaining, est_remaining_tickets, ev_per_dollar)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            game.game_id,
            now.isoformat(),
            game.top_prizes_remaining,
            game.all_prizes_remaining,
            game.estimated_remaining_tickets,
            game.ev_per_dollar,
        ),
    )
    return cur.lastrowid


def insert_prize_tiers(conn: sqlite3.Connection, snapshot_id: int, game: Game):
    conn.executemany(
        """
        INSERT INTO prize_tiers
            (snapshot_id, game_id, prize_value, start_count, remaining_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (snapshot_id, game.game_id, t.prize_value, t.start_count, t.remaining_count)
            for t in game.prize_tiers
        ],
    )


def mark_inactive(conn: sqlite3.Connection, active_ids: set[str]):
    """Mark any previously-active game that didn't appear in the latest scrape."""
    conn.execute(
        "UPDATE games SET is_active = 0 WHERE is_active = 1 AND game_id NOT IN ({})".format(
            ",".join("?" * len(active_ids))
        ),
        list(active_ids),
    )


def save_scrape_run(conn: sqlite3.Connection, games: list[Game]):
    """Persist a full scrape run inside a single transaction."""
    now = datetime.utcnow()
    with conn:
        for game in games:
            upsert_game(conn, game, now)
            snapshot_id = insert_snapshot(conn, game, now)
            insert_prize_tiers(conn, snapshot_id, game)
        mark_inactive(conn, {g.game_id for g in games})
