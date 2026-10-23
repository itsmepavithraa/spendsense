"""Shared test setup.

By default tests run against a throwaway SQLite file and fake Razorpay credentials,
so they need no Docker, no Postgres and no internet. In CI a second job points
TEST_DATABASE_URL at a real Postgres (with migrations applied) to also test the
Postgres-only parts such as the subscription-detection SQL view.

The environment variables must be set BEFORE the app is imported, because settings
are read at import time.
"""
import os
import sys
import tempfile
from pathlib import Path

_db_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", f"sqlite:///{Path(_db_dir, 'test.db').as_posix()}"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["RAZORPAY_KEY_ID"] = "rzp_test_key"
os.environ["RAZORPAY_KEY_SECRET"] = "test_key_secret"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_webhook_secret"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make `import app` work

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

IS_POSTGRES = os.environ["DATABASE_URL"].startswith("postgresql")

# tests that need Postgres features (SQL views) are skipped on SQLite
requires_postgres = pytest.mark.skipif(
    not IS_POSTGRES, reason="needs PostgreSQL (set TEST_DATABASE_URL)"
)


@pytest.fixture()
def client():
    from app.database import Base, engine
    from app.main import app

    if IS_POSTGRES:
        # tables and views come from the Alembic migrations; just empty the data
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE users, transactions, payments RESTART IDENTITY CASCADE"))
    else:
        Base.metadata.drop_all(engine)  # every test starts from empty tables
        Base.metadata.create_all(engine)
    with TestClient(app) as test_client:  # `with` keeps one event loop (needed for WebSockets)
        yield test_client


def register_and_login(client: TestClient, email: str = "user@test.com") -> dict:
    """Create a user and return the Authorization header for them."""
    client.post(
        "/auth/register",
        json={"email": email, "full_name": "Test User", "password": "password123"},
    )
    token = client.post(
        "/auth/login", data={"username": email, "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def token_of(headers: dict) -> str:
    return headers["Authorization"].split(" ", 1)[1]
