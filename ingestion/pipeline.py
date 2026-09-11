"""Extracts NBA player game logs and loads raw records into PostgreSQL via dlt."""
from __future__ import annotations

import argparse
import logging
import sys
from json import JSONDecodeError
from typing import Any, Iterator

import dlt
import requests
from nba_api.stats.endpoints import playergamelogs
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("ingestion.pipeline")

# Full header profile matching modern browser sessions to prevent Akamai throttling
NBA_API_HEADERS = {
    "Host": "stats.nba.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
    "Referer": "https://www.nba.com/stats",
    "Origin": "https://www.nba.com",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Connection": "keep-alive",
}

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.RequestException,
    requests.exceptions.Timeout,
    requests.exceptions.ConnectionError,
    requests.exceptions.HTTPError,
    JSONDecodeError,
)


@retry(
    reraise=True,
    stop=stop_after_attempt(6),
    wait=wait_random_exponential(multiplier=2, min=3, max=45),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    before_sleep=before_sleep_log(LOGGER, logging.WARNING),
)
def fetch_player_game_logs_with_retry(season: str) -> list[dict[str, Any]]:
    """Fetch player game logs from stats.nba.com with automated exponential retries."""
    LOGGER.info("Requesting player game logs from stats.nba.com for season %s...", season)

    logs = playergamelogs.PlayerGameLogs(
        season_nullable=season,
        season_type_nullable="Regular Season",
        headers=NBA_API_HEADERS,
        timeout=90,  # Allow NBA servers up to 90s to compile full-season payloads
    )

    data = logs.get_normalized_dict()
    records: list[dict[str, Any]] = data.get("PlayerGameLogs", [])

    if not records:
        LOGGER.warning("No records returned by stats.nba.com for season %s", season)
        return []

    LOGGER.info("Successfully extracted %d records for season %s", len(records), season)
    return records


@dlt.resource(
    name="player_game_logs",
    write_disposition="merge",
    primary_key=("GAME_ID", "PLAYER_ID"),
)
def player_game_logs_resource(season: str) -> Iterator[dict[str, Any]]:
    """Yield extracted player game records into dlt."""
    records = fetch_player_game_logs_with_retry(season=season)
    for record in records:
        record["season_id"] = season
        yield record


def run_pipeline(season: str) -> None:
    """Run dlt pipeline to load raw game logs into PostgreSQL."""
    pipeline = dlt.pipeline(
        pipeline_name="nba_lakehouse_ingestion",
        destination="postgres",
        dataset_name="raw_nba",
    )

    LOGGER.info("Starting dlt ingestion pipeline for season %s...", season)
    load_info = pipeline.run(
        player_game_logs_resource(season=season),
        table_name="player_game_logs",
    )
    LOGGER.info("dlt pipeline run completed: %s", load_info)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest NBA player game logs into PostgreSQL.")
    parser.add_argument(
        "--season",
        type=str,
        default="2024-25",
        help="Target NBA season formatted as YYYY-YY (e.g. 2024-25)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        run_pipeline(season=args.season)
    except Exception as error:
        LOGGER.critical("Ingestion pipeline failed fatally: %s", error, exc_info=True)
        sys.exit(1)