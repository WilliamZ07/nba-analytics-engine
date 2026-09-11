WITH base AS (
    SELECT * FROM {{ ref('player_game_stats') }}
)

SELECT
    player_id,
    player_name,
    season_id,
    MAX(team_abbreviation) AS latest_team,
    COUNT(DISTINCT game_id) AS games_played,
    COUNT(CASE WHEN wl = 'W' THEN 1 END) AS total_wins,
    COUNT(CASE WHEN wl = 'L' THEN 1 END) AS total_losses,
    ROUND(
        COUNT(CASE WHEN wl = 'W' THEN 1.0 END) / NULLIF(COUNT(DISTINCT game_id), 0),
        3
    ) AS win_percentage,
    ROUND(AVG(points), 2) AS ppg,
    ROUND(AVG(rebounds), 2) AS rpg,
    ROUND(AVG(assists), 2) AS apg,
    ROUND(AVG(steals), 2) AS spg,
    ROUND(AVG(blocks), 2) AS bpg,
    ROUND(AVG(turnovers), 2) AS tpg,
    COALESCE(
        ROUND(
            SUM(points)::NUMERIC / NULLIF(2 * (SUM(field_goals_attempted) + 0.44 * SUM(free_throws_attempted)), 0),
            3
        ),
        0.000
    ) AS true_shooting_pct
FROM base
GROUP BY player_id, player_name, season_id