with source as (
    select * from {{ source('raw_nba', 'player_game_logs') }}
),

renamed as (
    select
        cast(game_id as text) as game_id,
        cast(player_id as bigint) as player_id,
        cast(source_season as text) as season_id,
        cast(season_id as text) as nba_season_id,
        source_season_type as season_type,
        cast(game_date as date) as game_date,
        cast(team_id as bigint) as team_id,
        player_name,
        team_abbreviation,
        matchup,
        wl as win_loss,
        min as minutes_played,
        cast(pts as integer) as points,
        cast(reb as integer) as rebounds,
        cast(ast as integer) as assists,
        cast(stl as integer) as steals,
        cast(blk as integer) as blocks,
        cast(tov as integer) as turnovers,
        cast(fgm as integer) as field_goals_made,
        cast(fga as integer) as field_goals_attempted,
        cast(fg3_m as integer) as three_point_field_goals_made,
        cast(fg3_a as integer) as three_point_field_goals_attempted,
        cast(ftm as integer) as free_throws_made,
        cast(fta as integer) as free_throws_attempted,
        cast(plus_minus as integer) as plus_minus
    from source
)

select * from renamed
