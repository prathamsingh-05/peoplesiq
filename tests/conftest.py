import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

# Isolated data dir per test session; must be set before app modules import.
_tmp = tempfile.mkdtemp(prefix="peopleiq_test_")
os.environ["PEOPLEIQ_DATA_DIR"] = _tmp
os.environ["PEOPLEIQ_ADMIN_PASSWORD"] = "test-admin-password-123"
os.environ.pop("ANTHROPIC_API_KEY", None)  # force deterministic engine in tests
os.environ["PEOPLEIQ_EMAIL_SENDING"] = "false"
os.environ["PEOPLEIQ_REVIEW_SAMPLE_RATE"] = "0"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anon_client():
    """A guaranteed-unauthenticated client.

    The session-scoped `client` fixture cannot be used for auth-gate tests:
    `auth_client` sets a persistent Authorization header on that same object,
    so once it has run, `client` is authenticated for the rest of the session.
    This fixture builds a fresh client per test with no credentials at all.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_client(client):
    response = client.post("/api/auth/login", json={
        "username": "admin", "password": "test-admin-password-123",
    })
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
