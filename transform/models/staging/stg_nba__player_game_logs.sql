WITH source AS (
    SELECT * FROM {{ source('raw_nba', 'player_game_logs') }}
),

renamed AS (
    SELECT
        game_id::BIGINT AS game_id,
        player_id::BIGINT AS player_id,
        player_name::TEXT AS player_name,
        team_id::BIGINT AS team_id,
        team_abbreviation::TEXT AS team_abbreviation,
        game_date::DATE AS game_date,
        matchup::TEXT AS matchup,
        wl::TEXT AS wl,
        min::NUMERIC(5, 2) AS minutes_played,
        pts::INT AS points,
        reb::INT AS rebounds,
        ast::INT AS assists,
        stl::INT AS steals,
        blk::INT AS blocks,
        tov::INT AS turnovers,
        fgm::INT AS field_goals_made,
        fga::INT AS field_goals_attempted,
        fg_pct::NUMERIC(5, 3) AS field_goal_pct,
        fg3_m::INT AS three_pointers_made,
        fg3_a::INT AS three_pointers_attempted,
        fg3_pct::NUMERIC(5, 3) AS three_point_pct,
        ftm::INT AS free_throws_made,
        fta::INT AS free_throws_attempted,
        ft_pct::NUMERIC(5, 3) AS free_throw_pct,
        plus_minus::INT AS plus_minus,
        season_id::TEXT AS season_id
    FROM source
)

SELECT * FROM renamed