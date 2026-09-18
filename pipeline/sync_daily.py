"""Automated incremental ingestion and transformation pipeline for NBA games."""
from __future__ import annotations

import datetime
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import psycopg2
from nba_api.stats.endpoints import leaguegamefinder, playergamelog
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:admin123@postgres:5432/lakehouse",
)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def get_latest_game_date(season: str) -> datetime.date | None:
    """Find the most recent game recorded in the warehouse for this season."""
    query = """
        SELECT MAX(game_date) AS latest_date
        FROM analytics.player_game_stats
        WHERE season_id = %s;
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (season,))
                res = cur.fetchone()
                return res[0] if res and res[0] else None
    except Exception as exc:
        LOGGER.warning("Could not query latest date: %s", exc)
        return None


def fetch_and_stage_games(season: str, season_type: str = "Regular Season", min_date: datetime.date | None = None) -> int:
    """Pull completed games from NBA API and upsert into lakehouse."""
    date_str = min_date.strftime("%m/%d/%Y") if min_date else ""
    LOGGER.info("Querying NBA API for %s (%s) since %s...", season, season_type, date_str or "season start")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.nba.com/",
        "Origin": "https://www.nba.com",
    }

    try:
        finder = playergamelog.PlayerGameLog(
            season=season,
            season_type_all_star=season_type,
            date_from_nullable=date_str,
            headers=headers,
            timeout=30,
        )
        df_players = finder.get_data_frames()[0]
    except Exception as exc:
        LOGGER.error("Failed to fetch game logs from NBA API: %s", exc)
        return 0

    if df_players.empty:
        LOGGER.info("No new games found for %s (%s).", season, season_type)
        return 0

    # Clean and filter out games on or before min_date
    df_players["GAME_DATE"] = pd.to_datetime(df_players["GAME_DATE"]).dt.date
    if min_date:
        df_players = df_players[df_players["GAME_DATE"] > min_date]

    if df_players.empty:
        LOGGER.info("Warehouse is already up-to-date with all completed games.")
        return 0

    LOGGER.info("Fetched %d player records across new games. Ingesting into database...", len(df_players))

    # Standardize column mappings for staging
    insert_sql = """
        INSERT INTO analytics.player_game_stats (
            player_game_id, game_id, game_date, season_id, player_id, player_name,
            team_id, team_abbreviation, matchup, wl, minutes_played, points,
            field_goals_made, field_goals_attempted, three_pointers_made, three_pointers_attempted,
            free_throws_made, free_throws_attempted, rebounds, assists, steals, blocks, turnovers
        ) VALUES %s
        ON CONFLICT (player_game_id) DO UPDATE SET
            points = EXCLUDED.points,
            minutes_played = EXCLUDED.minutes_played,
            rebounds = EXCLUDED.rebounds,
            assists = EXCLUDED.assists;
    """

    records = []
    for _, r in df_players.iterrows():
        p_id = int(r["PLAYER_ID"])
        g_id = int(r["Game_ID"])
        pg_id = f"{g_id}_{p_id}"
        records.append((
            pg_id,
            g_id,
            r["GAME_DATE"],
            season,
            p_id,
            str(r["PLAYER_NAME"]),
            int(r["TEAM_ID"]),
            str(r["TEAM_ABBREVIATION"]),
            str(r["MATCHUP"]),
            str(r["WL"]),
            float(r.get("MIN") or 0.0),
            int(r.get("PTS") or 0),
            int(r.get("FGM") or 0),
            int(r.get("FGA") or 0),
            int(r.get("FG3M") or 0),
            int(r.get("FG3A") or 0),
            int(r.get("FTM") or 0),
            int(r.get("FTA") or 0),
            int(r.get("REB") or 0),
            int(r.get("AST") or 0),
            int(r.get("STL") or 0),
            int(r.get("BLK") or 0),
            int(r.get("TOV") or 0),
        ))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, insert_sql, records, page_size=1000)

    LOGGER.info("Successfully ingested %d player game entries.", len(records))
    return len(records)


def run_pipeline(season: str = "2024-25", include_playoffs: bool = True) -> None:
    """Run full ETL + dbt refresh + cache flush cycle."""
    latest_date = get_latest_game_date(season)
    
    # 1. Sync Regular Season
    new_reg = fetch_and_stage_games(season, "Regular Season", min_date=latest_date)
    
    # 2. Sync Playoffs (if applicable)
    new_post = 0
    if include_playoffs:
        time.sleep(1.5)  # Rate-limit safety
        new_post = fetch_and_stage_games(season, "Playoffs", min_date=latest_date)

    if new_reg == 0 and new_post == 0:
        LOGGER.info("No updates required. Exiting pipeline.")
        return

    # 3. Refresh dbt analytics models
    LOGGER.info("Executing dbt build to update cumulative ratings and feature tables...")
    dbt_exit = os.system("dbt build --project-dir transform --profiles-dir transform")
    if dbt_exit != 0:
        LOGGER.error("dbt build failed!")
        return

    # 4. Invalidate Redis Cache so Streamlit instantly reflects new data
    LOGGER.info("Flushing Redis endpoint cache...")
    try:
        httpx.delete(f"{API_BASE_URL}/cache", timeout=5.0)
    except Exception as exc:
        LOGGER.warning("Could not flush cache via API: %s", exc)

    LOGGER.info("Daily sync cycle completed successfully.")


def get_current_nba_season() -> str:
    """Calculate the active NBA season string dynamically from today's date."""
    today = datetime.date.today()
    start_year = today.year if today.month >= 10 else today.year - 1
    end_year_short = str(start_year + 1)[-2:]
    return f"{start_year}-{end_year_short}"


if __name__ == "__main__":
    # If a specific season argument was provided, use it; otherwise detect the active season automatically
    if len(sys.argv) > 1 and sys.argv[1] != "auto":
        target_season = sys.argv[1]
    else:
        target_season = get_current_nba_season()

    LOGGER.info("Daily Sync Target Season: %s", target_season)
    run_pipeline(season=target_season)