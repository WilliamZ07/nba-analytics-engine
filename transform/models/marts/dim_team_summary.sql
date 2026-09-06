with player_game_stats as (
    select * from {{ ref('player_game_stats') }}
),

team_game_aggregates as (
    select
        team_id,
        team_abbreviation,
        season_id,
        game_id,
        game_date,
        win_loss,
        sum(points) as team_points
    from player_game_stats
    group by team_id, team_abbreviation, season_id, game_id, game_date, win_loss
)

select
    team_id,
    team_abbreviation,
    season_id,
    count(distinct game_id) as games_played,
    count(case when win_loss = 'W' then 1 end) as wins,
    count(case when win_loss = 'L' then 1 end) as losses,
    round(count(case when win_loss = 'W' then 1 end)::numeric / nullif(count(*), 0), 3) as win_percentage,
    round(avg(team_points)::numeric, 2) as ppg
from team_game_aggregates
group by team_id, team_abbreviation, season_id