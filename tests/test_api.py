"""Automated API route, telemetry, and contract tests with mock database support."""
from __future__ import annotations

from typing import Any
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_database_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock database query responses so CI runs reliably without requiring pre-populated dbt tables."""

    def fake_fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        q = query.lower()

        # Platform / Health Check
        if "select 1 as database_ok" in q:
            return [{"database_ok": 1}]

        # Distinct Seasons
        if "select distinct season_id" in q:
            return [{"season_id": "2024-25"}, {"season_id": "2023-24"}]

        # Team Summary Mart
        if "dim_team_summary" in q:
            return [
                {
                    "team_id": 1610612738,
                    "team_abbreviation": "BOS",
                    "season_id": "2024-25",
                    "games_played": 82,
                    "wins": 64,
                    "losses": 18,
                    "win_percentage": 0.78,
                    "points_per_game": 120.6,
                }
            ]

        # Player Summary Mart
        if "dim_player_season_summary" in q:
            return [
                {
                    "player_id": 2544,
                    "player_name": "LeBron James",
                    "latest_team": "LAL",
                    "team_abbreviation": "LAL",
                    "season_id": "2024-25",
                    "games_played": 71,
                    "total_wins": 47,
                    "total_losses": 24,
                    "win_percentage": 0.662,
                    "points_per_game": 25.7,
                    "ppg": 25.7,
                    "rpg": 7.3,
                    "apg": 8.3,
                    "spg": 1.3,
                    "bpg": 0.5,
                    "tpg": 3.5,
                    "true_shooting_pct": 61.2,
                }
            ]

        # Surging Players Mart
        if "scoring_surge_differential" in q and "latest_game_per_player" in q:
            return [
                {
                    "player_id": 2544,
                    "player_name": "LeBron James",
                    "team_abbreviation": "LAL",
                    "rolling_10_pts_avg": 27.2,
                    "scoring_surge_differential": 3.4,
                }
            ]

        # Team Advanced Ratings Mart
        if "dim_team_advanced_ratings" in q and "def_rank" not in q:
            return [
                {
                    "team_id": 1610612747,
                    "team_abbreviation": "LAL",
                    "season_id": "2024-25",
                    "games_played": 82,
                    "wins": 47,
                    "losses": 35,
                    "win_percentage": 0.573,
                    "pace": 100.5,
                    "offensive_rating": 115.2,
                    "defensive_rating": 114.1,
                    "net_rating": 1.1,
                    "strength_of_schedule": 0.2,
                    "adjusted_offensive_rating": 115.0,
                    "adjusted_defensive_rating": 114.0,
                    "adjusted_net_rating": 1.0,
                }
            ]

        # Player Contextual Splits
        if "player_games_context" in q or "split_category" in q:
            return [
                {
                    "split_category": "Location",
                    "split_name": "Home",
                    "games": 35,
                    "ppg": 26.1,
                    "rpg": 7.5,
                    "apg": 8.5,
                    "spg": 1.2,
                    "bpg": 0.6,
                    "true_shooting_pct": 62.0,
                    "win_pct": 65.0,
                }
            ]

        # Game Schedule & Matched Games
        if "matched_games" in q:
            return [
                {
                    "game_id": "0022400001",
                    "game_date": "2024-10-22",
                    "season_id": "2024-25",
                    "home_team": "BOS",
                    "away_team": "NYK",
                    "home_score": 132,
                    "away_score": 109,
                    "home_wl": "W",
                    "pace": 98.5,
                    "game_possessions": 100.0,
                    "home_off_rtg": 132.0,
                    "away_off_rtg": 109.0,
                }
            ]

        # Single Game Box Score (Team Lines & Player Lines)
        if "player_game_stats" in q:
            if "sum(p.points)" in q:
                return [
                    {
                        "game_id": "0022400001",
                        "game_date": "2024-10-22",
                        "season_id": "2024-25",
                        "team_id": 1610612738,
                        "team_abbreviation": "BOS",
                        "matchup": "BOS vs. NYK",
                        "wl": "W",
                        "points": 132,
                        "fgm": 48,
                        "fga": 85,
                        "fg3_m": 29,
                        "fg3_a": 61,
                        "ftm": 7,
                        "fta": 9,
                        "rebounds": 40,
                        "assists": 33,
                        "steals": 7,
                        "blocks": 4,
                        "turnovers": 7,
                        "location": "HOME",
                        "game_possessions": 98.0,
                        "pace": 98.0,
                        "offensive_rating": 134.7,
                        "defensive_rating": 111.2,
                    }
                ]
            return [
                {
                    "player_id": 1628369,
                    "player_name": "Jayson Tatum",
                    "team_id": 1610612738,
                    "team_abbreviation": "BOS",
                    "minutes_played": 30.0,
                    "points": 37,
                    "rebounds": 4,
                    "assists": 10,
                    "steals": 1,
                    "blocks": 1,
                    "turnovers": 1,
                    "fgm": 14,
                    "fga": 18,
                    "fg3_m": 8,
                    "fg3_a": 11,
                    "ftm": 1,
                    "fta": 2,
                    "true_shooting_pct": 98.0,
                }
            ]

        return []

    monkeypatch.setattr("api.main.fetch_all", fake_fetch_all)


# ---------------------------------------------------------
# Test Cases (All 12 Original Tests Preserved)
# ---------------------------------------------------------

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_telemetry_headers():
    response = client.get("/health")
    assert response.status_code == 200
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    assert any(h in headers_lower for h in ["x-process-time", "x-process-time-ms", "x-request-id"])


def test_custom_request_id_propagation():
    custom_id = "test-request-id-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    headers_lower = {k.lower(): v for k, v in response.headers.items()}
    assert headers_lower.get("x-request-id") == custom_id


def test_list_teams():
    response = client.get("/teams?season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_list_players_search_filter():
    response = client.get("/players?search=LeBron&season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_surging_players_endpoint():
    response = client.get("/analytics/surging-players?limit=5&season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_team_advanced_ratings():
    response = client.get("/teams/1610612747/ratings?season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_team_ratings_sorting():
    response = client.get("/analytics/team-ratings?season=2024-25&sort_by=adjusted_net_rating")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_invalid_season_param_validation():
    response = client.get("/teams?season=invalid-format")
    assert response.status_code == 422


def test_player_splits_endpoint():
    response = client.get("/players/2544/splits?season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_games_endpoint():
    response = client.get("/games?season=2024-25&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_game_boxscore_endpoint():
    games_resp = client.get("/games?season=2024-25&limit=1")
    assert games_resp.status_code == 200
    games = games_resp.json()
    assert len(games) > 0

    game_id = games[0]["game_id"]
    box_resp = client.get(f"/games/{game_id}/boxscore")
    assert box_resp.status_code == 200
    box_data = box_resp.json()
    assert "teams" in box_data
    assert "players" in box_data