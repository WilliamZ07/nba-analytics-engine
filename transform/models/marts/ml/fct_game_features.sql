{{
    config(
        materialized='table',
        indexes=[
            {'columns': ['game_id'], 'unique': True},
            {'columns': ['game_date']},
            {'columns': ['season_id']}
        ]
    )
}}

WITH team_game_chronology AS (
    SELECT
        game_id,
        game_date,
        season_id,
        team_id,
        team_abbreviation,
        opponent_team_id,
        opponent_team_abbreviation,
        matchup,
        wl,
        points_scored AS points,
        points_allowed AS opponent_points,
        point_differential,
        game_possessions,
        pace,
        offensive_rating,
        defensive_rating,
        net_rating,
        CASE WHEN matchup LIKE '%@%' THEN 'AWAY' ELSE 'HOME' END AS location,
        -- Prior games played counter within season
        ROW_NUMBER() OVER (
            PARTITION BY team_id, season_id
            ORDER BY game_date ASC, game_id ASC
        ) - 1 AS prior_games_played,
        -- Rest days calculation (clamped to 5 days max to prevent early-season outlier distortion)
        COALESCE(
            LEAST(
                (game_date - LAG(game_date, 1) OVER (
                    PARTITION BY team_id, season_id
                    ORDER BY game_date ASC, game_id ASC
                ))::INTEGER - 1,
                5
            ),
            3
        ) AS rest_days,
        -- Rolling 10-Game Metrics (Strictly PRECEDING games to prevent data leakage)
        ROUND(
            AVG(offensive_rating) OVER (
                PARTITION BY team_id, season_id
                ORDER BY game_date ASC, game_id ASC
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
            )::NUMERIC,
            2
        ) AS rolling_10_off_rating,
        ROUND(
            AVG(defensive_rating) OVER (
                PARTITION BY team_id, season_id
                ORDER BY game_date ASC, game_id ASC
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
            )::NUMERIC,
            2
        ) AS rolling_10_def_rating,
        ROUND(
            AVG(net_rating) OVER (
                PARTITION BY team_id, season_id
                ORDER BY game_date ASC, game_id ASC
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
            )::NUMERIC,
            2
        ) AS rolling_10_net_rating,
        ROUND(
            AVG(pace) OVER (
                PARTITION BY team_id, season_id
                ORDER BY game_date ASC, game_id ASC
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
            )::NUMERIC,
            2
        ) AS rolling_10_pace,
        ROUND(
            AVG(CASE WHEN wl = 'W' THEN 1.0 ELSE 0.0 END) OVER (
                PARTITION BY team_id, season_id
                ORDER BY game_date ASC, game_id ASC
                ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
            )::NUMERIC,
            3
        ) AS rolling_10_win_pct
    FROM {{ ref('fct_team_game_stats') }}
),

home_teams AS (
    SELECT *
    FROM team_game_chronology
    WHERE location = 'HOME'
),

away_teams AS (
    SELECT *
    FROM team_game_chronology
    WHERE location = 'AWAY'
)

SELECT
    h.game_id,
    h.game_date,
    h.season_id,

    -- Team Identifiers
    h.team_id AS home_team_id,
    h.team_abbreviation AS home_team,
    a.team_id AS away_team_id,
    a.team_abbreviation AS away_team,

    -- Sample Maturity Flags (Games 1-9 lack a full 10-game baseline)
    h.prior_games_played AS home_prior_games,
    a.prior_games_played AS away_prior_games,
    CASE
        WHEN h.prior_games_played >= 10 AND a.prior_games_played >= 10 THEN 1
        ELSE 0
    END AS is_mature_sample,

    -- Schedule Fatigue Features
    h.rest_days AS home_rest_days,
    a.rest_days AS away_rest_days,
    (h.rest_days - a.rest_days) AS rest_differential,
    CASE WHEN h.rest_days = 0 THEN 1 ELSE 0 END AS is_home_back_to_back,
    CASE WHEN a.rest_days = 0 THEN 1 ELSE 0 END AS is_away_back_to_back,

    -- Team Rolling 10 Baseline Metrics
    h.rolling_10_off_rating AS home_l10_off_rating,
    h.rolling_10_def_rating AS home_l10_def_rating,
    h.rolling_10_net_rating AS home_l10_net_rating,
    h.rolling_10_pace AS home_l10_pace,
    h.rolling_10_win_pct AS home_l10_win_pct,

    a.rolling_10_off_rating AS away_l10_off_rating,
    a.rolling_10_def_rating AS away_l10_def_rating,
    a.rolling_10_net_rating AS away_l10_net_rating,
    a.rolling_10_pace AS away_l10_pace,
    a.rolling_10_win_pct AS away_l10_win_pct,

    -- Matchup Differential Features (Core ML Signals)
    ROUND((h.rolling_10_net_rating - a.rolling_10_net_rating)::NUMERIC, 2) AS net_rating_differential_l10,
    ROUND((h.rolling_10_off_rating - a.rolling_10_def_rating)::NUMERIC, 2) AS home_off_vs_away_def_edge,
    ROUND((a.rolling_10_off_rating - h.rolling_10_def_rating)::NUMERIC, 2) AS away_off_vs_home_def_edge,
    ROUND(((h.rolling_10_pace + a.rolling_10_pace) / 2.0)::NUMERIC, 2) AS projected_matchup_pace,
    ROUND((h.rolling_10_win_pct - a.rolling_10_win_pct)::NUMERIC, 3) AS win_pct_differential_l10,

    -- Ground Truth Target Labels (Used strictly for training and validation)
    CASE WHEN h.wl = 'W' THEN 1 ELSE 0 END AS target_home_win,
    (h.points - a.points) AS target_point_margin,
    (h.points + a.points) AS target_total_points

FROM home_teams h
INNER JOIN away_teams a
    ON h.game_id = a.game_id
ORDER BY h.game_date ASC, h.game_id ASC