"""
Scoring module — reads the latest snapshot from the DB and returns a
ranked DataFrame with EV and secondary signals for every active game.
"""

import sqlite3
import pandas as pd


def get_latest_scores(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Return one row per active game with EV score and secondary signals,
    computed from the most recent snapshot for each game.
    """
    df = pd.read_sql_query(
        """
        WITH ranked AS (
            SELECT
                s.*,
                ROW_NUMBER() OVER (PARTITION BY s.game_id ORDER BY s.scraped_at DESC) AS rn
            FROM snapshots s
        )
        SELECT
            g.game_id,
            g.name,
            g.price,
            g.top_prize,
            g.launch_date,
            g.est_total_tickets,
            r.scraped_at,
            r.top_prizes_remaining,
            r.all_prizes_remaining,
            r.est_remaining_tickets,
            r.ev_per_dollar
        FROM games g
        JOIN ranked r ON r.game_id = g.game_id AND r.rn = 1
        WHERE g.is_active = 1
        ORDER BY r.ev_per_dollar DESC
        """,
        conn,
    )

    # ── Secondary signals ──────────────────────────────────────────────────

    # Fraction of the print run still unsold (higher = game is newer / less depleted)
    df["tickets_remaining_pct"] = (
        df["est_remaining_tickets"] / df["est_total_tickets"].replace(0, pd.NA)
    ).clip(0, 1)

    # Game completion: how far through the print run we are (higher = near end)
    df["completion_pct"] = 1 - df["tickets_remaining_pct"]

    # Top prize density: top prizes left per 1 million remaining tickets
    df["top_prize_density"] = (
        df["top_prizes_remaining"]
        / df["est_remaining_tickets"].replace(0, pd.NA)
        * 1_000_000
    )

    # All-prize density: all prizes left per 1 million remaining tickets
    df["all_prize_density"] = (
        df["all_prizes_remaining"]
        / df["est_remaining_tickets"].replace(0, pd.NA)
        * 1_000_000
    )

    # Anomaly score: prizes depleting slower than tickets → positive means
    # more prizes proportionally remain than tickets (prizes "running behind")
    prizes_remaining_pct = (
        df["all_prizes_remaining"] / df["all_prizes_remaining"].replace(0, pd.NA)
    )
    # Re-derive from a ratio relative to the first snapshot's all_prizes count
    # (We approximate using est_total_tickets / probability_denom ≈ total_prizes)
    # Simpler proxy: compare rank of completion_pct vs rank of all_prizes_remaining_pct
    df["anomaly_score"] = (
        df["all_prizes_remaining"] / df["all_prizes_remaining"].max()
    ) - (
        df["est_remaining_tickets"] / df["est_total_tickets"].replace(0, pd.NA)
    ).fillna(0)

    return df.reset_index(drop=True)


def get_prize_tiers(conn: sqlite3.Connection, game_id: str) -> pd.DataFrame:
    """Latest prize tier breakdown for a single game."""
    return pd.read_sql_query(
        """
        SELECT pt.prize_value, pt.start_count, pt.remaining_count,
               pt.start_count - pt.remaining_count AS claimed_count,
               ROUND(100.0 * pt.remaining_count / NULLIF(pt.start_count, 0), 1)
                   AS pct_remaining
        FROM prize_tiers pt
        JOIN snapshots s ON s.id = pt.snapshot_id
        WHERE pt.game_id = ?
          AND s.scraped_at = (
              SELECT MAX(scraped_at) FROM snapshots WHERE game_id = ?
          )
        ORDER BY pt.prize_value DESC
        """,
        conn,
        params=(game_id, game_id),
    )


def get_ev_history(conn: sqlite3.Connection, game_ids: list[str]) -> pd.DataFrame:
    """
    Return the full snapshot history for a set of games, suitable for a
    multi-line EV-over-time chart.
    """
    if not game_ids:
        return pd.DataFrame()
    placeholders = ",".join("?" * len(game_ids))
    return pd.read_sql_query(
        f"""
        SELECT s.game_id, g.name, s.scraped_at, s.ev_per_dollar
        FROM snapshots s
        JOIN games g ON g.game_id = s.game_id
        WHERE s.game_id IN ({placeholders})
        ORDER BY s.scraped_at ASC
        """,
        conn,
        params=game_ids,
        parse_dates=["scraped_at"],
    )


def get_snapshot_history(conn: sqlite3.Connection, game_id: str) -> pd.DataFrame:
    """All snapshots for a game, for trend charts."""
    return pd.read_sql_query(
        """
        SELECT scraped_at, ev_per_dollar, top_prizes_remaining,
               all_prizes_remaining, est_remaining_tickets
        FROM snapshots
        WHERE game_id = ?
        ORDER BY scraped_at ASC
        """,
        conn,
        params=(game_id,),
    )
