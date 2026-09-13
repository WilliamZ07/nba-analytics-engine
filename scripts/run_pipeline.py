"""Automated end-to-end pipeline orchestrator for NBA Lakehouse."""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from typing import Any

from api.cache import get_redis_client
from ingestion.pipeline import run_pipeline as run_dlt_ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("orchestration.runner")


def run_command(command: list[str], step_name: str) -> None:
    """Execute a system command and stream output, failing on non-zero exit."""
    LOGGER.info("Starting step [%s]: %s", step_name, " ".join(command))
    start_time = time.perf_counter()

    result = subprocess.run(command, check=False)
    duration = round(time.perf_counter() - start_time, 2)

    if result.returncode != 0:
        LOGGER.error(
            "Step [%s] failed with exit code %d after %.2fs",
            step_name,
            result.returncode,
            duration,
        )
        sys.exit(result.returncode)

    LOGGER.info("Step [%s] completed successfully in %.2fs", step_name, duration)


def flush_redis_cache() -> int:
    """Clear all cached endpoint entries from Redis."""
    LOGGER.info("Starting cache invalidation...")
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis client unavailable; skipping cache flush.")
        return 0

    try:
        keys = client.keys("nba_api:*")
        if keys:
            deleted_count = client.delete(*keys)
            LOGGER.info("Successfully flushed %d cached keys from Redis.", deleted_count)
            return deleted_count
        LOGGER.info("No cached keys found matching pattern 'nba_api:*'.")
        return 0
    except Exception as exc:
        LOGGER.warning("Failed to flush Redis cache: %s", exc)
        return 0


def orchestrate_pipeline(season: str, skip_ingest: bool = False) -> None:
    """Execute the full data platform lifecycle in strict sequence."""
    pipeline_start = time.perf_counter()
    summary: dict[str, Any] = {
        "season": season,
        "steps": {},
        "status": "RUNNING",
    }

    LOGGER.info("==================================================")
    LOGGER.info("Starting NBA Lakehouse Pipeline Orchestrator")
    LOGGER.info("Target Season: %s", season)
    LOGGER.info("==================================================")

    # 1. Ingestion Step
    if not skip_ingest:
        step_start = time.perf_counter()
        LOGGER.info("--- Step 1/4: Ingestion (dlt + nba_api) ---")
        try:
            run_dlt_ingestion(season=season)
            summary["steps"]["ingestion"] = {
                "status": "SUCCESS",
                "duration_seconds": round(time.perf_counter() - step_start, 2),
            }
        except Exception as exc:
            LOGGER.critical("Ingestion failed fatally: %s", exc, exc_info=True)
            summary["steps"]["ingestion"] = {
                "status": "FAILED",
                "error": str(exc),
                "duration_seconds": round(time.perf_counter() - step_start, 2),
            }
            summary["status"] = "FAILED"
            print(json.dumps(summary, indent=2))
            sys.exit(1)
    else:
        LOGGER.info("--- Step 1/4: Ingestion [SKIPPED] ---")
        summary["steps"]["ingestion"] = {"status": "SKIPPED"}

    # 2. Transformation & Data Quality Step
    step_start = time.perf_counter()
    LOGGER.info("--- Step 2/4: Transformation & Schema Testing (dbt) ---")
    project_dir = os.getenv("DBT_PROJECT_DIR", "/app/transform")
    dbt_command = [
        "dbt",
        "build",
        "--project-dir",
        project_dir,
        "--profiles-dir",
        project_dir,
    ]
    run_command(dbt_command, "dbt_build")
    summary["steps"]["transformation_and_quality"] = {
        "status": "SUCCESS",
        "duration_seconds": round(time.perf_counter() - step_start, 2),
    }

    # 3. Cache Invalidation Step
    step_start = time.perf_counter()
    LOGGER.info("--- Step 3/4: Cache Invalidation (Redis) ---")
    cleared_keys = flush_redis_cache()
    summary["steps"]["cache_invalidation"] = {
        "status": "SUCCESS",
        "keys_cleared": cleared_keys,
        "duration_seconds": round(time.perf_counter() - step_start, 2),
    }

    # 4. API Integration Test Step
    step_start = time.perf_counter()
    LOGGER.info("--- Step 4/4: API Integration Verification (pytest) ---")
    pytest_command = ["pytest", "tests/", "-v"]
    run_command(pytest_command, "api_integration_tests")
    summary["steps"]["api_verification"] = {
        "status": "SUCCESS",
        "duration_seconds": round(time.perf_counter() - step_start, 2),
    }

    total_duration = round(time.perf_counter() - pipeline_start, 2)
    summary["status"] = "SUCCESS"
    summary["total_duration_seconds"] = total_duration

    LOGGER.info("==================================================")
    LOGGER.info("Pipeline Execution Completed Successfully in %.2fs", total_duration)
    LOGGER.info("Execution Summary:\n%s", json.dumps(summary, indent=2))
    LOGGER.info("==================================================")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end NBA Lakehouse data pipeline orchestrator."
    )
    parser.add_argument(
        "--season",
        type=str,
        default="2024-25",
        help="Target NBA season formatted as YYYY-YY (e.g. 2024-25)",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip API ingestion and only run transformation, cache flush, and tests.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    orchestrate_pipeline(season=args.season, skip_ingest=args.skip_ingest)