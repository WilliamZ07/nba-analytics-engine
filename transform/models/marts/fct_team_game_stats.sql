WITH team_game_totals AS (
    SELECT
        game_id,
        team_id,
        team_abbreviation,
        season_id,
        game_date,
        matchup,
        wl,
        SUM(minutes_played) AS team_minutes,
        SUM(points) AS points_scored,
        SUM(field_goals_made) AS fgm,
        SUM(field_goals_attempted) AS fga,
        SUM(three_pointers_made) AS fg3_m,
        SUM(three_pointers_attempted) AS fg3_a,
        SUM(free_throws_made) AS ftm,
        SUM(free_throws_attempted) AS fta,
        SUM(rebounds) AS reb,
        SUM(assists) AS ast,
        SUM(steals) AS stl,
        SUM(blocks) AS blk,
        SUM(turnovers) AS tov
    FROM {{ ref('player_game_stats') }}
    GROUP BY game_id, team_id, team_abbreviation, season_id, game_date, matchup, wl
),

game_matchups AS (
    SELECT
        t.game_id,
        t.team_id,
        t.team_abbreviation,
        t.season_id,
        t.game_date,
        t.matchup,
        t.wl,
        t.team_minutes,
        t.points_scored,
        opp.team_id AS opponent_team_id,
        opp.team_abbreviation AS opponent_team_abbreviation,
        opp.points_scored AS points_allowed,
        ROUND(
            0.5 * (
                (t.fga + 0.44 * t.fta + t.tov - 0.3 * t.reb) +
                (opp.fga + 0.44 * opp.fta + opp.tov - 0.3 * opp.reb)
            ),
            2
        ) AS game_possessions
    FROM team_game_totals t
    INNER JOIN team_game_totals opp
        ON t.game_id = opp.game_id
       AND t.team_id != opp.team_id
)

SELECT
    CONCAT(game_id, '-', team_id) AS team_game_id,
    game_id,
    team_id,
    team_abbreviation,
    opponent_team_id,
    opponent_team_abbreviation,
    season_id,
    game_date,
    matchup,
    wl,
    points_scored,
    points_allowed,
    (points_scored - points_allowed) AS point_differential,
    game_possessions,
    ROUND(
        48.0 * game_possessions / NULLIF(team_minutes / 5.0, 0),
        2
    ) AS pace,
    ROUND(
        100.0 * points_scored / NULLIF(game_possessions, 0),
        2
    ) AS offensive_rating,
    ROUND(
        100.0 * points_allowed / NULLIF(game_possessions, 0),
        2
    ) AS defensive_rating,
    ROUND(
        (100.0 * points_scored / NULLIF(game_possessions, 0)) -
        (100.0 * points_allowed / NULLIF(game_possessions, 0)),
        2
    ) AS net_rating
FROM game_matchups