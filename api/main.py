"""HTTP interface for curated NBA analytics data."""
from __future__ import annotations

import logging
import sys
from typing import Annotated, Any
import psycopg2
from fastapi import FastAPI, HTTPException, Query, status
from psycopg2.extras import RealDictCursor

from api.cache import cache_endpoint, get_redis_client
from api.database import get_db_connection
from api.middleware import StructuredLoggingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 1000

app = FastAPI(
    title="NBA Lakehouse API",
    version="0.4.0",
    description="Read-only endpoints backed by dbt-curated NBA analytics marts and Redis caching.",
)

app.add_middleware(StructuredLoggingMiddleware)


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
            detail=f"Database query failed: {error}",
        ) from error
    finally:
        if connection is not None:
            connection.close()


@app.get("/", tags=["platform"])
def read_root() -> dict[str, str]:
    return {"status": "healthy", "service": "nba-lakehouse-api", "version": "0.4.0"}


@app.get("/health", tags=["platform"])
def health_check() -> dict[str, str]:
    fetch_all("SELECT 1 AS database_ok;")
    redis_client = get_redis_client()
    redis_ok = bool(redis_client and redis_client.ping())
    return {
        "status": "healthy",
        "database": "connected",
        "cache": "connected" if redis_ok else "disabled",
    }


@app.delete("/cache", tags=["platform"])
def flush_cache() -> dict[str, str]:
    """Flush all cached query responses from Redis."""
    redis_client = get_redis_client()
    if redis_client:
        keys = redis_client.keys("nba_api:*")
        if keys:
            redis_client.delete(*keys)
        return {"status": "cleared", "keys_removed": str(len(keys))}
    return {"status": "bypassed", "detail": "cache unavailable"}


@app.get("/players", tags=["players"])
@cache_endpoint(ttl_seconds=1800)
def list_players(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    search: str | None = Query(default=None, min_length=2, max_length=80),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 1000,
) -> list[dict[str, Any]]:
    search_term = f"%{search.strip()}%" if search and search.strip() else None
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
        ORDER BY player_name ASC
        LIMIT %s;
        """,
        (season, season, search_term, search_term, limit),
    )


@app.get("/players/{player_id}/summary", tags=["players"])
@cache_endpoint(ttl_seconds=1800)
def player_season_summary(
    player_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
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
@cache_endpoint(ttl_seconds=900)
def player_game_log(
    player_id: int,
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 82,
) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            r.game_id,
            r.game_date,
            r.season_id,
            r.player_id,
            r.player_name,
            r.team_abbreviation,
            p.matchup,
            p.wl,
            p.minutes_played,
            r.points,
            p.field_goals_made AS fgm,
            p.field_goals_attempted AS fga,
            p.three_pointers_made AS fg3_m,
            p.three_pointers_attempted AS fg3_a,
            p.free_throws_made AS ftm,
            p.free_throws_attempted AS fta,
            r.rebounds,
            r.assists,
            p.steals,
            p.blocks,
            p.turnovers,
            ROUND(
                p.points::NUMERIC / NULLIF(2.0 * (p.field_goals_attempted + 0.44 * p.free_throws_attempted), 0) * 100,
                1
            ) AS true_shooting_pct,
            r.rolling_10_pts_avg,
            r.scoring_surge_differential
        FROM analytics.fct_player_rolling_stats r
        INNER JOIN analytics.player_game_stats p
            ON r.player_game_id = p.player_game_id
        WHERE r.player_id = %s
          AND (%s IS NULL OR r.season_id = %s)
        ORDER BY r.game_date DESC, r.game_id DESC
        LIMIT %s;
        """,
        (player_id, season, season, limit),
    )


@app.get("/players/{player_id}/splits", tags=["players"])
@cache_endpoint(ttl_seconds=1800)
def player_splits(
    player_id: int,
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
    return fetch_all(
        """
        WITH ranked_defenses AS (
            SELECT
                team_id,
                season_id,
                RANK() OVER (PARTITION BY season_id ORDER BY adjusted_defensive_rating ASC) AS def_rank
            FROM analytics.dim_team_advanced_ratings
            WHERE season_id = %s
        ),
        player_games_context AS (
            SELECT
                p.game_id,
                p.season_id,
                p.matchup,
                p.wl,
                p.points,
                p.rebounds,
                p.assists,
                p.steals,
                p.blocks,
                p.field_goals_made,
                p.field_goals_attempted,
                p.free_throws_attempted,
                CASE WHEN p.matchup LIKE '%%@%%' THEN 'Away' ELSE 'Home' END AS location_split,
                CASE WHEN p.wl = 'W' THEN 'Wins' ELSE 'Losses' END AS outcome_split,
                CASE
                    WHEN rd.def_rank <= 10 THEN 'vs Top 10 Defenses'
                    WHEN rd.def_rank >= 21 THEN 'vs Bottom 10 Defenses'
                    ELSE 'vs Middle Tier Defenses'
                END AS opponent_tier_split
            FROM analytics.player_game_stats p
            INNER JOIN analytics.fct_team_game_stats ft
                ON p.game_id = ft.game_id AND p.team_id = ft.team_id
            INNER JOIN ranked_defenses rd
                ON ft.opponent_team_id = rd.team_id AND ft.season_id = rd.season_id
            WHERE p.player_id = %s AND p.season_id = %s
        ),
        location_agg AS (
            SELECT
                'Location' AS split_category,
                location_split AS split_name,
                COUNT(*) AS games,
                ROUND(AVG(points), 1) AS ppg,
                ROUND(AVG(rebounds), 1) AS rpg,
                ROUND(AVG(assists), 1) AS apg,
                ROUND(AVG(steals), 1) AS spg,
                ROUND(AVG(blocks), 1) AS bpg,
                ROUND(SUM(points)::NUMERIC / NULLIF(2.0 * (SUM(field_goals_attempted) + 0.44 * SUM(free_throws_attempted)), 0) * 100, 1) AS true_shooting_pct,
                ROUND(SUM(CASE WHEN wl = 'W' THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_pct
            FROM player_games_context
            GROUP BY location_split
        ),
        outcome_agg AS (
            SELECT
                'Outcome' AS split_category,
                outcome_split AS split_name,
                COUNT(*) AS games,
                ROUND(AVG(points), 1) AS ppg,
                ROUND(AVG(rebounds), 1) AS rpg,
                ROUND(AVG(assists), 1) AS apg,
                ROUND(AVG(steals), 1) AS spg,
                ROUND(AVG(blocks), 1) AS bpg,
                ROUND(SUM(points)::NUMERIC / NULLIF(2.0 * (SUM(field_goals_attempted) + 0.44 * SUM(free_throws_attempted)), 0) * 100, 1) AS true_shooting_pct,
                ROUND(SUM(CASE WHEN wl = 'W' THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_pct
            FROM player_games_context
            GROUP BY outcome_split
        ),
        tier_agg AS (
            SELECT
                'Opponent Defense Quality' AS split_category,
                opponent_tier_split AS split_name,
                COUNT(*) AS games,
                ROUND(AVG(points), 1) AS ppg,
                ROUND(AVG(rebounds), 1) AS rpg,
                ROUND(AVG(assists), 1) AS apg,
                ROUND(AVG(steals), 1) AS spg,
                ROUND(AVG(blocks), 1) AS bpg,
                ROUND(SUM(points)::NUMERIC / NULLIF(2.0 * (SUM(field_goals_attempted) + 0.44 * SUM(free_throws_attempted)), 0) * 100, 1) AS true_shooting_pct,
                ROUND(SUM(CASE WHEN wl = 'W' THEN 1 ELSE 0 END)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS win_pct
            FROM player_games_context
            GROUP BY opponent_tier_split
        )
        SELECT * FROM location_agg
        UNION ALL
        SELECT * FROM outcome_agg
        UNION ALL
        SELECT * FROM tier_agg
        ORDER BY split_category, split_name;
        """,
        (season, player_id, season),
    )


@app.get("/teams", tags=["teams"])
@cache_endpoint(ttl_seconds=3600)
def list_teams(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
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


@app.get("/teams/{team_id}/ratings", tags=["teams"])
@cache_endpoint(ttl_seconds=3600)
def team_advanced_ratings(
    team_id: int,
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
) -> list[dict[str, Any]]:
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
            pace,
            offensive_rating,
            defensive_rating,
            net_rating,
            strength_of_schedule,
            adjusted_offensive_rating,
            adjusted_defensive_rating,
            adjusted_net_rating
        FROM analytics.dim_team_advanced_ratings
        WHERE team_id = %s AND season_id = %s;
        """,
        (team_id, season),
    )


@app.get("/analytics/team-ratings", tags=["analytics"])
@cache_endpoint(ttl_seconds=3600)
def list_team_ratings(
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
    sort_by: str = Query(
        default="adjusted_net_rating",
        pattern=r"^(adjusted_net_rating|adjusted_defensive_rating|adjusted_offensive_rating|pace)$",
    ),
) -> list[dict[str, Any]]:
    order_clause = "ASC" if sort_by == "adjusted_defensive_rating" else "DESC"
    query = f"""
        SELECT
            team_id,
            team_abbreviation,
            season_id,
            wins,
            losses,
            win_percentage,
            pace,
            offensive_rating,
            defensive_rating,
            net_rating,
            strength_of_schedule,
            adjusted_offensive_rating,
            adjusted_defensive_rating,
            adjusted_net_rating
        FROM analytics.dim_team_advanced_ratings
        WHERE season_id = %s
        ORDER BY {sort_by} {order_clause};
    """
    return fetch_all(query, (season,))


@app.get("/analytics/surging-players", tags=["analytics"])
@cache_endpoint(ttl_seconds=600)
def surging_players(
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 10,
) -> list[dict[str, Any]]:
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


@app.get("/games", tags=["games"])
@cache_endpoint(ttl_seconds=1800)
def list_games(
    season: str = Query(default="2024-25", pattern=r"^\d{4}-\d{2}$"),
    team: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> list[dict[str, Any]]:
    """List completed games with scores, matchup, and pace metrics."""
    team_clean = team.strip().upper() if team and team.strip() else None
    return fetch_all(
        """
        WITH team_game_summary AS (
            SELECT
                p.game_id,
                p.game_date,
                p.season_id,
                p.team_abbreviation,
                p.matchup,
                p.wl,
                SUM(p.points) AS total_points,
                CASE WHEN p.matchup LIKE '%%@%%' THEN 'AWAY' ELSE 'HOME' END AS location,
                ft.game_possessions,
                ft.pace,
                ft.offensive_rating,
                ft.defensive_rating
            FROM analytics.player_game_stats p
            LEFT JOIN analytics.fct_team_game_stats ft
                ON p.game_id = ft.game_id AND p.team_id = ft.team_id
            WHERE p.season_id = %s
            GROUP BY
                p.game_id, p.game_date, p.season_id, p.team_abbreviation,
                p.matchup, p.wl, ft.game_possessions, ft.pace, ft.offensive_rating, ft.defensive_rating
        ),
        matched_games AS (
            SELECT
                h.game_id,
                h.game_date,
                h.season_id,
                h.team_abbreviation AS home_team,
                a.team_abbreviation AS away_team,
                h.total_points AS home_score,
                a.total_points AS away_score,
                h.wl AS home_wl,
                h.pace,
                h.game_possessions,
                h.offensive_rating AS home_off_rtg,
                a.offensive_rating AS away_off_rtg
            FROM team_game_summary h
            INNER JOIN team_game_summary a
                ON h.game_id = a.game_id AND h.team_abbreviation != a.team_abbreviation
            WHERE h.location = 'HOME'
        )
        SELECT *
        FROM matched_games
        WHERE (%s IS NULL OR home_team = %s OR away_team = %s)
        ORDER BY game_date DESC, game_id DESC
        LIMIT %s;
        """,
        (season, team_clean, team_clean, team_clean, limit),
    )


@app.get("/games/{game_id}/boxscore", tags=["games"])
@cache_endpoint(ttl_seconds=3600)
def game_boxscore(game_id: str) -> dict[str, Any]:
    """Return comprehensive single-game box score: team telemetry and all individual player lines."""
    team_stats = fetch_all(
        """
        SELECT
            p.game_id,
            p.game_date,
            p.season_id,
            p.team_id,
            p.team_abbreviation,
            p.matchup,
            p.wl,
            SUM(p.points) AS points,
            SUM(p.field_goals_made) AS fgm,
            SUM(p.field_goals_attempted) AS fga,
            SUM(p.three_pointers_made) AS fg3_m,
            SUM(p.three_pointers_attempted) AS fg3_a,
            SUM(p.free_throws_made) AS ftm,
            SUM(p.free_throws_attempted) AS fta,
            SUM(p.rebounds) AS rebounds,
            SUM(p.assists) AS assists,
            SUM(p.steals) AS steals,
            SUM(p.blocks) AS blocks,
            SUM(p.turnovers) AS turnovers,
            CASE WHEN p.matchup LIKE '%%@%%' THEN 'AWAY' ELSE 'HOME' END AS location,
            ft.game_possessions,
            ft.pace,
            ft.offensive_rating,
            ft.defensive_rating
        FROM analytics.player_game_stats p
        LEFT JOIN analytics.fct_team_game_stats ft
            ON p.game_id = ft.game_id AND p.team_id = ft.team_id
        WHERE p.game_id = %s
        GROUP BY
            p.game_id, p.game_date, p.season_id, p.team_id, p.team_abbreviation,
            p.matchup, p.wl, ft.game_possessions, ft.pace, ft.offensive_rating, ft.defensive_rating;
        """,
        (game_id,),
    )

    if not team_stats:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Game {game_id} not found.")

    players = fetch_all(
        """
        SELECT
            player_id,
            player_name,
            team_id,
            team_abbreviation,
            minutes_played,
            points,
            rebounds,
            assists,
            steals,
            blocks,
            turnovers,
            field_goals_made AS fgm,
            field_goals_attempted AS fga,
            three_pointers_made AS fg3_m,
            three_pointers_attempted AS fg3_a,
            free_throws_made AS ftm,
            free_throws_attempted AS fta,
            ROUND(
                points::NUMERIC / NULLIF(2.0 * (field_goals_attempted + 0.44 * free_throws_attempted), 0) * 100,
                1
            ) AS true_shooting_pct
        FROM analytics.player_game_stats
        WHERE game_id = %s
        ORDER BY team_abbreviation, points DESC, minutes_played DESC;
        """,
        (game_id,),
    )

    return {
        "game_id": game_id,
        "teams": team_stats,
        "players": players,
    }