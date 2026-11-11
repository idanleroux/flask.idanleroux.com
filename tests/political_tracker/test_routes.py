"""Route smoke tests for Political Tracker.

Every route must return 200 both with and without database data.
Tests that need Postgres skip cleanly when DATABASE_URL is unset.
"""
from __future__ import annotations

import os

import pytest
from flask import Flask

from main import app


@pytest.fixture
def client():
    app.testing = True
    return app.test_client()


# Routes that must return 200 without any database
NO_DB_ROUTES = [
    "/",
    "/political_tracker",
    "/political_tracker/about",
    "/political_view_US",
    "/political_view_UK",
    "/political_view_US/compare",
    "/political_view_UK/compare",
]


@pytest.mark.parametrize("path", NO_DB_ROUTES)
def test_routes_without_db(client, path):
    """Every public route returns 200 even when the database is unavailable."""
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"


# API routes should return empty results without DB
API_ROUTES = [
    ("/political_view_US/api/members?q=smith", {"results": []}),
    ("/political_view_UK/api/members?q=smith", {"results": []}),
    ("/political_view_US/api/map/house", {"features": []}),
    ("/political_view_UK/api/map", {"features": []}),
]


@pytest.mark.parametrize("path,expected", API_ROUTES)
def test_api_routes_without_db(client, path, expected):
    """JSON API routes return empty results when DB is unavailable."""
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    data = r.get_json()
    assert data == expected, f"{path} returned {data}, expected {expected}"


# Routes needing a database (skip when no live DB)
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping live DB route tests",
)
@pytest.mark.parametrize("path", NO_DB_ROUTES)
def test_routes_with_db(client, path):
    """Every public route returns 200 with a live database."""
    r = client.get(path)
    assert r.status_code == 200
