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
    version="0.2.0",
    description="Read-only endpoints backed by dbt-curated NBA analytics marts.",
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
    return {"status": "healthy", "service": "nba-lakehouse-api", "version": "0.2.0"}


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
            player_name,
            latest_team AS team_abbreviation,
            games_played,
            ppg AS points_per_game,
            apg AS assists_per_game,
            rpg AS rebounds_per_game,
            true_shooting_pct
        FROM analytics.dim_player_season_summary
        WHERE (%s IS NULL OR season_id = %s)
          AND (%s IS NULL OR player_name ILIKE %s)
        ORDER BY points_per_game DESC NULLS LAST, player_name
        LIMIT %s;
        """,
        (season, season, search_term, search_term, limit),
    )


@app.get("/players/{player_id}/summary", tags=["players"])
def player_season_summary(
    player_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
    """Return detailed season-by-season performance summary and true-shooting metrics."""
    return fetch_all(
        """
        SELECT
            player_id,
            player_name,
            season_id,
            latest_team,
            games_played,
            total_wins,
            total_losses,
            win_percentage,
            ppg,
            rpg,
            apg,
            spg,
            bpg,
            tpg,
            true_shooting_pct
        FROM analytics.dim_player_season_summary
        WHERE player_id = %s
          AND (%s IS NULL OR season_id = %s)
        ORDER BY season_id DESC;
        """,
        (player_id, season, season),
    )


@app.get("/players/{player_id}/games", tags=["players"])
def player_game_log(
    player_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Return a player's individual games with rolling 10-game window metrics."""
    return fetch_all(
        """
        SELECT
            game_id,
            game_date,
            season_id,
            player_id,
            player_name,
            team_abbreviation,
            points,
            assists,
            rebounds,
            rolling_10_pts_avg,
            rolling_10_ast_avg,
            rolling_10_reb_avg,
            scoring_surge_differential
        FROM analytics.fct_player_rolling_stats
        WHERE player_id = %s
          AND (%s IS NULL OR season_id = %s)
        ORDER BY game_date DESC, game_id DESC
        LIMIT %s;
        """,
        (player_id, season, season, limit),
    )


@app.get("/teams", tags=["teams"])
def list_teams(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
    """Return team win-loss standings and scoring metrics."""
    return fetch_all(
        """
        SELECT
            team_id,
            team_abbreviation,
            season_id,
            games_played,
            wins,
            losses,
            win_percentage,
            ppg AS points_per_game
        FROM analytics.dim_team_summary
        WHERE (%s IS NULL OR season_id = %s)
        ORDER BY win_percentage DESC, wins DESC;
        """,
        (season, season),
    )


@app.get("/teams/{team_id}/leaders", tags=["teams"])
def team_stat_leaders(
    team_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[dict[str, Any]]:
    """Return leading scorers for a specified team."""
    return fetch_all(
        """
        SELECT
            player_id,
            player_name,
            season_id,
            games_played,
            ppg,
            rpg,
            apg,
            true_shooting_pct
        FROM analytics.dim_player_season_summary
        WHERE latest_team = (SELECT team_abbreviation FROM analytics.dim_team_summary WHERE team_id = %s LIMIT 1)
          AND (%s IS NULL OR season_id = %s)
        ORDER BY ppg DESC
        LIMIT %s;
        """,
        (team_id, season, season, limit),
    )


@app.get("/analytics/surging-players", tags=["analytics"])
def surging_players(
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 10,
) -> list[dict[str, Any]]:
    """Return players with the highest positive scoring differential over their last 10 games."""
    return fetch_all(
        """
        WITH latest_game_per_player AS (
            SELECT
                player_id,
                player_name,
                team_abbreviation,
                rolling_10_pts_avg,
                scoring_surge_differential,
                ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY game_date DESC, game_id DESC) AS rn
            FROM analytics.fct_player_rolling_stats
            WHERE season_id = %s
        )
        SELECT
            player_id,
            player_name,
            team_abbreviation,
            rolling_10_pts_avg,
            scoring_surge_differential
        FROM latest_game_per_player
        WHERE rn = 1 AND scoring_surge_differential IS NOT NULL
        ORDER BY scoring_surge_differential DESC
        LIMIT %s;
        """,
        (season, limit),
    )