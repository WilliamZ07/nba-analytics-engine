"""Integration tests for NBA Lakehouse REST API."""
import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_telemetry_headers():
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert "x-response-time-ms" in response.headers
    assert float(response.headers["x-response-time-ms"]) >= 0.0


def test_custom_request_id_propagation():
    custom_id = "test-req-trace-12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


def test_list_teams():
    response = client.get("/teams?season=2024-25")
    assert response.status_code == 200
    teams = response.json()
    assert isinstance(teams, list)
    if len(teams) > 0:
        team = teams[0]
        assert "team_id" in team
        assert "team_abbreviation" in team
        assert "win_percentage" in team


def test_list_players_search_filter():
    response = client.get("/players?search=LeBron&season=2024-25")
    assert response.status_code == 200
    players = response.json()
    assert isinstance(players, list)
    if len(players) > 0:
        assert "LeBron" in players[0]["player_name"]


def test_surging_players_endpoint():
    response = client.get("/analytics/surging-players?limit=5&season=2024-25")
    assert response.status_code == 200
    surging = response.json()
    assert isinstance(surging, list)
    assert len(surging) <= 5
    if len(surging) > 0:
        assert "scoring_surge_differential" in surging[0]


def test_invalid_season_param_validation():
    response = client.get("/players?season=invalid-season")
    assert response.status_code == 422