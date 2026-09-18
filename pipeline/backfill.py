"""Batch backfill historical NBA seasons and playoffs into PostgreSQL."""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.sync_daily import fetch_and_stage_games

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
LOGGER = logging.getLogger(__name__)

# Default range: 2019-20 to 2024-25 (6 complete modern seasons)
DEFAULT_SEASONS = [
    "2019-20",
    "2020-21",
    "2021-22",
    "2022-23",
    "2023-24",
    "2024-25",
]


def generate_season_range(start_year: int, end_year: int) -> list[str]:
    """Generate NBA season strings like ['2018-19', '2019-20', ...]"""
    seasons = []
    for y in range(start_year, end_year + 1):
        next_short = str(y + 1)[-2:]
        seasons.append(f"{y}-{next_short}")
    return seasons


def run_batch_backfill(seasons: list[str], include_playoffs: bool = True) -> None:
    """Ingest a list of seasons and run dbt build + ML retraining at the end."""
    LOGGER.info("Starting historical backfill for %d seasons: %s", len(seasons), seasons)

    total_records = 0
    for idx, season in enumerate(seasons, 1):
        LOGGER.info("==================================================")
        LOGGER.info("[%d/%d] Ingesting Season: %s", idx, len(seasons), season)
        LOGGER.info("==================================================")

        # 1. Regular Season
        reg_count = fetch_and_stage_games(season=season, season_type="Regular Season", min_date=None)
        total_records += reg_count
        time.sleep(1.5)  # Safe NBA API throttling delay

        # 2. Playoffs
        if include_playoffs:
            post_count = fetch_and_stage_games(season=season, season_type="Playoffs", min_date=None)
            total_records += post_count
            time.sleep(1.5)

    LOGGER.info("All raw games loaded! Total player lines inserted/updated: %d", total_records)

    # 3. Transform the entire warehouse at once
    LOGGER.info("Building dbt dimensional marts and feature stores across all seasons...")
    dbt_status = os.system("dbt build --project-dir transform --profiles-dir transform")
    if dbt_status != 0:
        LOGGER.error("dbt build failed. Check transform logs.")
        return

    # 4. Retrain Machine Learning Models with multi-year data
    LOGGER.info("Retraining ML Win Probability & Spread models on expanded multi-year dataset...")
    ml_status = os.system("python ml/train_model.py")
    if ml_status != 0:
        LOGGER.warning("ML training had issues. Please verify ml/artifacts/.")

    LOGGER.info("Batch backfill completed successfully!")


if __name__ == "__main__":
    # If custom years passed via CLI (e.g. 'python pipeline/backfill.py 2018 2024')
    if len(sys.argv) >= 3:
        start_y = int(sys.argv[1])
        end_y = int(sys.argv[2])
        target_seasons = generate_season_range(start_y, end_y)
    else:
        target_seasons = DEFAULT_SEASONS

    run_batch_backfill(target_seasons, include_playoffs=True)