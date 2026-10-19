"""
tests/test_notifications.py

Run from project root:
    pytest tests/test_notifications.py -v
"""
import os
import sys
import pytest

# ── env vars before any app import ──────────────────────────────────────────
os.environ["JWT_SECRET"]             = "test-secret-key"
os.environ["JWT_ALGORITHM"]          = "HS256"
os.environ["JWT_EXPIRY_MINUTES"]     = "60"
os.environ["INTERNAL_SERVICE_TOKEN"] = "internal-test-token"

# ── inject SQLite engine before app import ───────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_conn   = _engine.connect()
_TestSession = sessionmaker(bind=_conn, autocommit=False, autoflush=False)

for _module_name in tuple(sys.modules):
    if _module_name == "app" or _module_name.startswith("app."):
        del sys.modules[_module_name]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "notification-service"))
import app.database as _db_module

_db_module.engine       = _engine
_db_module.SessionLocal = _TestSession

from app.models import Notification
from app.database import Base
Base.metadata.create_all(bind=_conn)

from app.main import app
from fastapi.testclient import TestClient

# ── auth helpers ─────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
from jose import jwt as _jwt

INTERNAL = {"authorization": "Bearer internal-test-token"}

def _user_token(user_id: int = 1, expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 60)
    return _jwt.encode({"sub": str(user_id), "role": "user", "exp": exp}, "test-secret-key", algorithm="HS256")

def _user_auth(user_id: int = 1) -> dict:
    return {"authorization": f"Bearer {_user_token(user_id)}"}

# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    _conn.execute(Notification.__table__.delete())
    _conn.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _post(client, user_id=1, booking_id=42, message="Booking confirmed", token=None):
    headers = {"authorization": f"Bearer {token}"} if token else INTERNAL
    return client.post(
        "/notifications/",
        json={"user_id": user_id, "booking_id": booking_id, "message": message},
        headers=headers,
    )


# ── health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "notification-service"


# ── POST /notifications/ ──────────────────────────────────────────────────────

def test_create_notification_success(client):
    r = _post(client)
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"]    == 1
    assert data["booking_id"] == 42
    assert data["message"]    == "Booking confirmed"
    assert data["status"]     == "sent"
    assert data["logical_clock"] >= 1


def test_create_notification_clock_increments(client):
    r1 = _post(client, booking_id=1)
    r2 = _post(client, booking_id=2)
    assert r2.json()["logical_clock"] > r1.json()["logical_clock"]


def test_create_notification_wrong_internal_token(client):
    r = _post(client, token="wrong-token")
    assert r.status_code == 401


def test_create_notification_user_jwt_rejected(client):
    """A user JWT must NOT be accepted on the internal endpoint."""
    r = _post(client, token=_user_token(1))
    assert r.status_code == 401


def test_create_notification_missing_auth(client):
    r = client.post("/notifications/", json={"user_id": 1, "booking_id": 1, "message": "x"})
    assert r.status_code == 422


# ── GET /notifications/my ─────────────────────────────────────────────────────

def test_my_notifications_empty(client):
    r = client.get("/notifications/my", headers=_user_auth(1))
    assert r.status_code == 200
    assert r.json() == []


def test_my_notifications_returns_own_only(client):
    _post(client, user_id=1, booking_id=10)
    _post(client, user_id=1, booking_id=11)
    _post(client, user_id=2, booking_id=20)

    r = client.get("/notifications/my", headers=_user_auth(1))
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(n["user_id"] == 1 for n in data)


def test_my_notifications_ordered_by_id(client):
    _post(client, booking_id=1)
    _post(client, booking_id=2)
    _post(client, booking_id=3)
    data = client.get("/notifications/my", headers=_user_auth(1)).json()
    ids = [n["id"] for n in data]
    assert ids == sorted(ids)


def test_my_notifications_internal_token_rejected(client):
    """Internal token must NOT work on the user-facing endpoint."""
    r = client.get("/notifications/my", headers=INTERNAL)
    assert r.status_code == 401


def test_my_notifications_expired_token(client):
    r = client.get(
        "/notifications/my",
        headers={"authorization": f"Bearer {_user_token(expired=True)}"},
    )
    assert r.status_code == 401


def test_my_notifications_invalid_token(client):
    r = client.get("/notifications/my", headers={"authorization": "Bearer not.a.token"})
    assert r.status_code == 401
