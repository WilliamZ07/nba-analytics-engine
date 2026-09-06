with player_game_stats as (
    select * from {{ ref('player_game_stats') }}
)

select
    player_id,
    season_id,
    max(player_name) as player_name,
    max(team_abbreviation) as latest_team,
    count(distinct game_id) as games_played,
    count(case when win_loss = 'W' then 1 end) as total_wins,
    count(case when win_loss = 'L' then 1 end) as total_losses,
    round(count(case when win_loss = 'W' then 1 end)::numeric / nullif(count(*), 0), 3) as win_percentage,
    round(avg(points)::numeric, 2) as ppg,
    round(avg(rebounds)::numeric, 2) as rpg,
    round(avg(assists)::numeric, 2) as apg,
    round(avg(steals)::numeric, 2) as spg,
    round(avg(blocks)::numeric, 2) as bpg,
    round(avg(turnovers)::numeric, 2) as tpg,
    sum(points) as total_points,
    sum(field_goals_made) as total_fgm,
    sum(field_goals_attempted) as total_fga,
    sum(three_point_field_goals_made) as total_fg3m,
    sum(three_point_field_goals_attempted) as total_fg3a,
    sum(free_throws_made) as total_ftm,
    sum(free_throws_attempted) as total_fta,
    case
        when (2 * (sum(field_goals_attempted) + 0.44 * sum(free_throws_attempted))) = 0 then 0
        else round(
            (sum(points)::numeric / (2 * (sum(field_goals_attempted) + 0.44 * sum(free_throws_attempted))))::numeric,
            3
        )
    end as true_shooting_pct
from player_game_stats
group by player_id, season_id