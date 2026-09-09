"""Integration test suite for the NBA Lakehouse API serving layer."""
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_check():
    """Ensure API and Postgres database connection are operational."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_list_teams():
    """Verify team standings return 30 teams and proper schema structure."""
    response = client.get("/teams?season=2024-25")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 30
    first_team = data[0]
    assert "team_abbreviation" in first_team
    assert "win_percentage" in first_team
    assert "points_per_game" in first_team
    assert first_team["win_percentage"] >= data[-1]["win_percentage"]


def test_list_players_search_filter():
    """Verify player filtering and search query matching."""
    response = client.get("/players?season=2024-25&search=LeBron&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any("LeBron James" in p["player_name"] for p in data)
    assert "true_shooting_pct" in data[0]


def test_surging_players_endpoint():
    """Verify surging players returns ranked differentials in descending order."""
    response = client.get("/analytics/surging-players?season=2024-25&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    differentials = [item["scoring_surge_differential"] for item in data]
    assert differentials == sorted(differentials, reverse=True)


def test_invalid_season_param_validation():
    """Ensure regex query validator rejects improperly formatted season strings."""
    response = client.get("/teams?season=202425")
    assert response.status_code == 422