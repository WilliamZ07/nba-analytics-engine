# NBA Lakehouse API

A local-first NBA analytics platform that loads player-level box scores from the NBA Stats API, automatically lands the raw data in PostgreSQL, transforms it with dbt, and exposes curated statistics through FastAPI.

It is intentionally designed as a strong portfolio project without a cloud bill. The same boundaries also make a later deployment straightforward: replace local PostgreSQL with a managed warehouse, schedule the two jobs, and deploy the API as a container.

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
```

`dlt` owns raw-table creation and schema evolution. dbt owns the business-facing data model. This separation is deliberate: raw API contracts change, while API consumers need stable curated columns.

## Stack

- Python and `nba_api` for extraction
- `dlt` for loading and automatic raw-schema inference
- PostgreSQL 16 for the local warehouse
- dbt-postgres for tested analytics transformations
- FastAPI and parameterized SQL for the serving layer
- Docker Compose for a reproducible local environment

## Run locally

Prerequisites: Docker Desktop and Python 3.12+ (Python is only needed if you prefer running jobs outside Docker).

1. Optionally copy `.env.example` to `.env` and change the local-only credentials.
2. Start the database:

   ```powershell
   docker compose up -d postgres
   ```

3. Load a season. The composite player-game key makes reruns idempotent while retaining previously loaded seasons:

   ```powershell
   docker compose run --rm ingest python -m ingestion.pipeline --season 2024-25
   ```

4. Build and test the curated dbt models:

   ```powershell
   docker compose run --rm transform
   ```

5. Start the API and open the interactive docs at <http://localhost:8000/docs>:

   ```powershell
   docker compose --profile api up -d api
   ```

Example endpoints:

```text
GET /health
GET /players?season=2024-25&search=Nikola
GET /players/203999/games?season=2024-25
```

To run the jobs from the host instead, create a virtual environment, install `requirements.txt`, keep Postgres running, then run `python -m ingestion.pipeline --season 2024-25` and `dbt build --project-dir transform --profiles-dir transform`.

## Project scope and next increments

This first vertical slice deliberately uses player game logs because it proves an end-to-end data contract while remaining fast to operate. Add complexity in focused increments:

1. Add game, team, and player dimension models; retain raw source data untouched.
2. Add a second extraction resource for box-score detail or play-by-play, then model it as an event fact table.
3. Add an orchestrator (Prefect or Airflow) only when there are multiple scheduled, monitored jobs.
4. Add API integration tests, pagination, caching, and a small frontend dashboard.
5. Deploy only after the local product is stable—e.g. API container on Render/Fly.io and managed Postgres or BigQuery. Keep the Terraform/AWS layer as an optional extension, not the project prerequisite.
