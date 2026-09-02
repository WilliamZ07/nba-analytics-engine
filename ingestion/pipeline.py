"""Load NBA player game logs into PostgreSQL with automatic schema inference.

Run from the repository root:
    python -m ingestion.pipeline --season 2024-25

``dlt`` creates and evolves the ``raw_nba`` schema; no hand-written raw-table DDL is required.
The transformation layer owns the curated analytics schema.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Iterator
from typing import Any
from urllib.parse import quote

import dlt
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)

DEFAULT_SEASON = "2024-25"
SEASON_TYPES = ("Regular Season", "Playoffs", "Pre Season", "All Star")

load_dotenv()


def get_player_game_logs(season: str, season_type: str) -> list[dict[str, Any]]:
    """Fetch one season of player-level box scores from NBA Stats."""
    try:
        from nba_api.stats.endpoints import leaguegamelog
    except ImportError as error:  # pragma: no cover - guarded by requirements
        raise RuntimeError(
            "nba_api is not installed. Run `pip install -r requirements.txt`."
        ) from error

    endpoint = leaguegamelog.LeagueGameLog(
        player_or_team_abbreviation="P",
        season=season,
        season_type_all_star=season_type,
        timeout=30,
    )
    result_sets = endpoint.get_dict().get("resultSets", [])
    if not result_sets:
        raise RuntimeError("NBA Stats returned no result sets.")

    result_set = result_sets[0]
    headers = result_set.get("headers", [])
    rows = result_set.get("rowSet", [])
    if not headers:
        raise RuntimeError("NBA Stats response did not include column headers.")

    records = [dict(zip(headers, row, strict=True)) for row in rows]
    if not records:
        raise RuntimeError(
            f"NBA Stats returned no player game logs for {season} ({season_type})."
        )
    return records


@dlt.resource(
    name="player_game_logs",
    primary_key=("GAME_ID", "PLAYER_ID"),
    write_disposition="merge",
)
def player_game_logs(season: str, season_type: str) -> Iterator[dict[str, Any]]:
    """Yield raw API records for dlt to normalize and load."""
    records = get_player_game_logs(season=season, season_type=season_type)
    LOGGER.info("Fetched %s player game logs for %s %s", len(records), season, season_type)
    for record in records:
        yield {
            **record,
            "source_season": season,
            "source_season_type": season_type,
        }


def postgres_destination() -> Any:
    """Build dlt's destination from local environment variables.

    An explicitly supplied destination URL still wins, which keeps Docker and
    hosted deployments compatible with dlt's standard configuration.
    """
    credentials = os.getenv("DESTINATION__POSTGRES__CREDENTIALS")
    if not credentials:
        username = quote(os.getenv("POSTGRES_USER", "admin"), safe="")
        password = quote(os.getenv("POSTGRES_PASSWORD", "adminpassword"), safe="")
        host = os.getenv("POSTGRES_HOST", "127.0.0.1")
        port = os.getenv("POSTGRES_PORT", "5433")
        database = os.getenv("POSTGRES_DB", "lakehouse")
        credentials = f"postgresql://{username}:{password}@{host}:{port}/{database}"
    return dlt.destinations.postgres(credentials=credentials)


def load_player_game_logs(season: str, season_type: str) -> Any:
    """Run the idempotent local ELT load and return dlt's load report."""
    pipeline = dlt.pipeline(
        pipeline_name="nba_player_game_logs",
        destination=postgres_destination(),
        dataset_name="raw_nba",
    )
    return pipeline.run(player_game_logs(season=season, season_type=season_type))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load NBA player game logs into the local PostgreSQL warehouse."
    )
    parser.add_argument("--season", default=DEFAULT_SEASON, help="NBA season, e.g. 2024-25")
    parser.add_argument(
        "--season-type",
        choices=SEASON_TYPES,
        default="Regular Season",
        help="NBA competition segment to ingest.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()
    load_info = load_player_game_logs(season=args.season, season_type=args.season_type)
    LOGGER.info("Load completed successfully.\n%s", load_info)


if __name__ == "__main__":
    main()