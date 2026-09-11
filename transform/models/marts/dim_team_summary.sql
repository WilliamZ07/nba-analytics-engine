WITH base AS (
    SELECT * FROM {{ ref('player_game_stats') }}
),

team_games AS (
    SELECT
        team_id,
        team_abbreviation,
        season_id,
        game_id,
        MAX(wl) AS wl,
        SUM(points) AS team_game_points
    FROM base
    GROUP BY team_id, team_abbreviation, season_id, game_id
)

SELECT
    team_id,
    team_abbreviation,
    season_id,
    COUNT(DISTINCT game_id) AS games_played,
    COUNT(CASE WHEN wl = 'W' THEN 1 END) AS wins,
    COUNT(CASE WHEN wl = 'L' THEN 1 END) AS losses,
    ROUND(
        COUNT(CASE WHEN wl = 'W' THEN 1.0 END) / NULLIF(COUNT(DISTINCT game_id), 0),
        3
    ) AS win_percentage,
    ROUND(AVG(team_game_points), 2) AS ppg
FROM team_games
GROUP BY team_id, team_abbreviation, season_id