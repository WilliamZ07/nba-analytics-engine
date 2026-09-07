with player_game_stats as (
    select * from {{ ref('player_game_stats') }}
),

player_season_stats as (
    select
        player_id,
        season_id,
        avg(points)::numeric as season_ppg
    from player_game_stats
    group by player_id, season_id
)

select
    f.player_game_id,
    f.player_id,
    f.player_name,
    f.team_abbreviation,
    f.game_id,
    f.game_date,
    f.season_id,
    f.points,
    f.assists,
    f.rebounds,
    round(
        avg(f.points) over (
            partition by f.player_id, f.season_id
            order by f.game_date asc, f.game_id asc
            rows between 9 preceding and current row
        )::numeric,
        2
    ) as rolling_10_pts_avg,
    round(
        avg(f.assists) over (
            partition by f.player_id, f.season_id
            order by f.game_date asc, f.game_id asc
            rows between 9 preceding and current row
        )::numeric,
        2
    ) as rolling_10_ast_avg,
    round(
        avg(f.rebounds) over (
            partition by f.player_id, f.season_id
            order by f.game_date asc, f.game_id asc
            rows between 9 preceding and current row
        )::numeric,
        2
    ) as rolling_10_reb_avg,
    round(
        (
            avg(f.points) over (
                partition by f.player_id, f.season_id
                order by f.game_date asc, f.game_id asc
                rows between 9 preceding and current row
            )::numeric - s.season_ppg
        ),
        2
    ) as scoring_surge_differential,
    row_number() over (
        partition by f.player_id, f.season_id
        order by f.game_date asc, f.game_id asc
    ) as game_sequence_number
from player_game_stats f
left join player_season_stats s
    on f.player_id = s.player_id and f.season_id = s.season_id