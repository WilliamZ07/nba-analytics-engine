"""HTTP interface for curated NBA analytics data."""

from __future__ import annotations

import logging
from typing import Annotated, Any

import psycopg2
from fastapi import FastAPI, HTTPException, Query, status
from psycopg2.extras import RealDictCursor

from api.database import get_db_connection

LOGGER = logging.getLogger(__name__)
DEFAULT_LIMIT = 25
MAX_LIMIT = 100

app = FastAPI(
    title="NBA Lakehouse API",
    version="0.1.0",
    description="Read-only endpoints backed by dbt-curated NBA player game statistics.",
)


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Run a parameterized read query and always release database resources."""
    connection = None
    try:
        connection = get_db_connection()
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())
    except psycopg2.Error as error:
        LOGGER.exception("Database query failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Analytics database is unavailable. Load and transform data before querying.",
        ) from error
    finally:
        if connection is not None:
            connection.close()


@app.get("/", tags=["platform"])
def read_root() -> dict[str, str]:
    return {"status": "healthy", "service": "nba-lakehouse-api"}


@app.get("/health", tags=["platform"])
def health_check() -> dict[str, str]:
    fetch_all("SELECT 1 AS database_ok;")
    return {"status": "healthy", "database": "connected"}


@app.get("/players", tags=["players"])
def list_players(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    search: str | None = Query(default=None, min_length=2, max_length=80),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Return player aggregates, optionally filtered by season or name."""
    search_term = f"%{search.strip()}%" if search else None
    return fetch_all(
        """
        SELECT
            player_id,
            MAX(player_name) AS player_name,
            COUNT(*) AS games_played,
            ROUND(AVG(points)::numeric, 2) AS points_per_game,
            ROUND(AVG(assists)::numeric, 2) AS assists_per_game,
            ROUND(AVG(rebounds)::numeric, 2) AS rebounds_per_game
        FROM analytics.player_game_stats
        WHERE (%s IS NULL OR season_id = %s)
          AND (%s IS NULL OR player_name ILIKE %s)
        GROUP BY player_id
        ORDER BY points_per_game DESC NULLS LAST, player_name
        LIMIT %s;
        """,
        (season, season, search_term, search_term, limit),
    )


@app.get("/players/{player_id}/games", tags=["players"])
def player_game_log(
    player_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Return a player's most recent games from the curated fact table."""
    return fetch_all(
        """
        SELECT
            game_id, game_date, season_id, player_id, player_name, team_abbreviation,
            matchup, win_loss, minutes_played, points, assists, rebounds,
            steals, blocks, turnovers, plus_minus
        FROM analytics.player_game_stats
        WHERE player_id = %s
          AND (%s IS NULL OR season_id = %s)
        ORDER BY game_date DESC, game_id DESC
        LIMIT %s;
        """,
        (player_id, season, season, limit),
    )
