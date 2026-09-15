WITH team_season_base AS (
    SELECT
        team_id,
        team_abbreviation,
        season_id,
        COUNT(DISTINCT game_id) AS games_played,
        COUNT(CASE WHEN wl = 'W' THEN 1 END) AS wins,
        COUNT(CASE WHEN wl = 'L' THEN 1 END) AS losses,
        SUM(points_scored) AS total_points_scored,
        SUM(points_allowed) AS total_points_allowed,
        SUM(game_possessions) AS total_possessions,
        ROUND(AVG(pace), 2) AS pace,
        ROUND(100.0 * SUM(points_scored) / NULLIF(SUM(game_possessions), 0), 2) AS offensive_rating,
        ROUND(100.0 * SUM(points_allowed) / NULLIF(SUM(game_possessions), 0), 2) AS defensive_rating,
        ROUND(
            (100.0 * SUM(points_scored) / NULLIF(SUM(game_possessions), 0)) -
            (100.0 * SUM(points_allowed) / NULLIF(SUM(game_possessions), 0)),
            2
        ) AS net_rating
    FROM {{ ref('fct_team_game_stats') }}
    GROUP BY team_id, team_abbreviation, season_id
),

league_baselines AS (
    SELECT
        season_id,
        AVG(offensive_rating) AS league_avg_off_rtg,
        AVG(defensive_rating) AS league_avg_def_rtg
    FROM team_season_base
    GROUP BY season_id
),

opponent_strength AS (
    SELECT
        f.team_id,
        f.season_id,
        AVG(opp.offensive_rating) AS avg_opponent_off_rtg,
        AVG(opp.defensive_rating) AS avg_opponent_def_rtg
    FROM {{ ref('fct_team_game_stats') }} f
    INNER JOIN team_season_base opp
        ON f.opponent_team_id = opp.team_id
       AND f.season_id = opp.season_id
    GROUP BY f.team_id, f.season_id
)

SELECT
    t.team_id,
    t.team_abbreviation,
    t.season_id,
    t.games_played,
    t.wins,
    t.losses,
    ROUND(t.wins::NUMERIC / NULLIF(t.games_played, 0), 3) AS win_percentage,
    t.pace,
    t.offensive_rating,
    t.defensive_rating,
    t.net_rating,
    ROUND(o.avg_opponent_off_rtg - l.league_avg_off_rtg, 2) AS strength_of_schedule,
    ROUND(
        t.offensive_rating + (l.league_avg_def_rtg - o.avg_opponent_def_rtg),
        2
    ) AS adjusted_offensive_rating,
    ROUND(
        t.defensive_rating - (o.avg_opponent_off_rtg - l.league_avg_off_rtg),
        2
    ) AS adjusted_defensive_rating,
    ROUND(
        (t.offensive_rating + (l.league_avg_def_rtg - o.avg_opponent_def_rtg)) -
        (t.defensive_rating - (o.avg_opponent_off_rtg - l.league_avg_off_rtg)),
        2
    ) AS adjusted_net_rating
FROM team_season_base t
INNER JOIN league_baselines l ON t.season_id = l.season_id
INNER JOIN opponent_strength o ON t.team_id = o.team_id AND t.season_id = o.season_id