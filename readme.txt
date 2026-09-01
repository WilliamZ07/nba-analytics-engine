# NBA Lakehouse API

A local-first NBA analytics platform that loads player-level box scores from the NBA Stats API, automatically lands the raw data in PostgreSQL, transforms it with dbt, and exposes curated statistics through FastAPI. 

It is intentionally designed as a project without using the cloud. The same boundaries also make a later deployment straightforward: replace local PostgreSQL with a managed warehouse, schedule the two jobs, and deploy the API as a container.

## Architecture

```text
NBA Stats API
    |  nba_api
    v
dlt ingestion job  --->  PostgreSQL: raw_nba (automatic schema inference)
                                  |
                                  | dbt build
                                  v
                         PostgreSQL: analytics.player_game_stats
                                  |
                                  v
                           FastAPI read API