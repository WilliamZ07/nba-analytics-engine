# dbt transformation layer

`raw_nba` is owned by dlt and mirrors the source contract. These models expose a stable `analytics.player_game_stats` fact table for the FastAPI service.

Run from the repository root after ingestion:
```powershell
dbt build --project-dir transform --profiles-dir transform