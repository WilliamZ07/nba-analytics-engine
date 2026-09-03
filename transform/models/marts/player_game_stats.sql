with player_game_logs as (
    select * from {{ ref('stg_nba__player_game_logs') }}
)

select
    concat(game_id, '-', player_id) as player_game_id,
    *
from player_game_logs
