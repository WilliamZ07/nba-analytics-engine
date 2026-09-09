# NBA Analytics Engine

A local-first NBA analytics platform that extracts player box scores from the NBA Stats API, automatically loads raw records into PostgreSQL with schema inference, transforms data into analytical marts using dbt, and serves curated statistics through FastAPI.

It is intentionally designed as a reproducible, zero-cost data platform without requiring active cloud infrastructure.

---

## Architecture

```text
NBA Stats API
    │
    │  nba_api (Python)
    ▼
dlt Ingestion Job  ───►  PostgreSQL (raw_nba.player_game_logs)
                               │
                               │  dbt build
                               ▼
                         PostgreSQL (analytics schema)
                           ├── stg_nba__player_game_logs
                           ├── player_game_stats
                           ├── dim_player_season_summary
                           ├── dim_team_summary
                           └── fct_player_rolling_stats
                               │
                               ▼
                         FastAPI Read API
```

* **Extraction & Ingestion:** `dlt` handles pipeline execution, automatic schema inference, and idempotent table merging (`write_disposition="merge"`).
* **Transformation & Data Modeling:** `dbt` standardizes field types, enforces relational integrity, and models dimensional summaries with calculated metrics like True Shooting Percentage ($TS\%$), 10-game rolling windows, and scoring surge differentials.
* **Serving Layer:** `FastAPI` exposes parameterized SQL queries via REST endpoints.

---

## Tech Stack

* **Ingestion:** Python 3.12, `dlt`, `nba_api`
* **Warehouse:** PostgreSQL 16 (Alpine)
* **Transformation:** `dbt-postgres`
* **Serving Layer:** FastAPI, Uvicorn, Psycopg2
* **Testing:** `dbt test`, `pytest`, `httpx`
* **Infrastructure:** Docker Compose

---

## Run Locally

### Prerequisites
* Docker Desktop
* Python 3.12+ (optional, if executing jobs outside Docker)

### 1. Environment Configuration
Copy the local environment template:
```powershell
cp .env.example .env
```

### 2. Start PostgreSQL Database
```powershell
docker compose up -d postgres
```

### 3. Ingest Season Data
Extract and load player game logs for a given NBA season:
```powershell
docker compose run --rm ingest python -m ingestion.pipeline --season 2024-25
```

### 4. Build and Test Analytics Models
Compile, materialize, and run schema assertion tests across staging views, base fact tables, and dimensional summary marts:
```powershell
docker compose run --rm transform dbt build --project-dir /app/transform --profiles-dir /app/transform
```

### 5. Launch Serving Layer
Start the API service and access interactive documentation at `http://localhost:8000/docs`:
```powershell
docker compose --profile api up -d api
```

### 6. Run Integration Test Suite
Execute the automated endpoint contract tests:
```powershell
docker compose run --rm api pytest tests/
```

---

## API Endpoints

| Method | Endpoint | Description | Query Parameters |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service and database connectivity check | None |
| `GET` | `/players` | Player season averages & $TS\%$ | `season`, `search`, `limit` |
| `GET` | `/players/{player_id}/summary` | Career/season stat totals and shooting metrics | `season` |
| `GET` | `/players/{player_id}/games` | Game log with 10-game rolling averages & surge | `season`, `limit` |
| `GET` | `/teams` | Regular season team standings and records | `season` |
| `GET` | `/teams/{team_id}/leaders` | Top scoring leaders for a specific team | `season`, `limit` |
| `GET` | `/analytics/surging-players` | Players with highest 10-game positive surge | `season`, `limit` |

---

## Data Models (v0.2.0)

* `analytics.stg_nba__player_game_logs`: Staging view normalizing and casting raw source columns.
* `analytics.player_game_stats`: Base fact table containing player-game box scores with a composite primary key (`game_id-player_id`).
* `analytics.dim_player_season_summary`: Player-level aggregations containing games played, win/loss records, per-game averages (PPG, RPG, APG, SPG, BPG, TPG), and True Shooting Percentage ($TS\%$).
* `analytics.dim_team_summary`: Team-level seasonal aggregations containing games played, records (wins, losses, win percentage), and team points per game.
* `analytics.fct_player_rolling_stats`: Analytical fact table containing trailing 10-game rolling averages and scoring surge differential metrics calculated via SQL window functions.

---

## Incremental Roadmap

* [x] **v0.1.0** — Local ELT baseline (`dlt` + `dbt`), PostgreSQL container, and FastAPI read endpoints.
* [x] **v0.2.0** — Analytics & Data Quality Layer:
  * [x] **v0.2.1** — Player and Team seasonal summary marts with True Shooting calculations.
  * [x] **v0.2.2** — 10-game rolling window calculations and scoring surge differentials.
  * [x] **v0.2.3** — Model schema assertions, uniqueness checks, and data quality tests (14 tests passing).
  * [x] **v0.2.4** — REST API serving layer expansion for summaries, standings, and leaders.
  * [x] **v0.2.5** — Automated integration testing with `pytest`.
* [ ] **v0.3.0** — Pipeline automation, logging, retries, and Redis caching.
* [ ] **v0.4.0** — Web dashboard and zero-cost cloud deployment.