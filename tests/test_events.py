"""
tests/test_events.py

Run from project root:
    pytest tests/test_events.py -v
"""
import os
import sys
import pytest

# ── env vars must be set before any app import ──────────────────────────────
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRY_MINUTES", "60")

# ── inject SQLite in-memory engine before importing the app ─────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_conn = _engine.connect()  # single persistent connection — avoids per-connection isolation

from sqlalchemy.orm import sessionmaker
_TestSession = sessionmaker(bind=_conn, autocommit=False, autoflush=False)

# Patch database module before app import
for _module_name in tuple(sys.modules):
    if _module_name == "app" or _module_name.startswith("app."):
        del sys.modules[_module_name]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "event-service"))
import app.database as _db_module

_db_module.engine       = _engine
_db_module.SessionLocal = _TestSession

# Now import models and create tables on the shared connection
from app.models import Event, Seat
from app.database import Base
Base.metadata.create_all(bind=_conn)

# Import app after DB is ready
from app.main import app
from fastapi.testclient import TestClient

# ── JWT helpers ──────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
from jose import jwt as _jwt

def _make_token(role: str = "user", user_id: int = 1, expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 60)
    return _jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, "test-secret-key", algorithm="HS256")

ADMIN_TOKEN = f"Bearer {_make_token('admin', 99)}"
USER_TOKEN  = f"Bearer {_make_token('user',  1)}"

# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def clean_db():
    """Wipe events (cascades to seats) before each test."""
    _conn.execute(Seat.__table__.delete())
    _conn.execute(Event.__table__.delete())
    _conn.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _create_event(client, token=ADMIN_TOKEN, **overrides):
    payload = {
        "name": "Test Event",
        "date": "2025-12-01",
        "time": "10:00:00",
        "venue": "Test Venue",
        "city": "Test City",
        "total_seats": 20,
        "price": "100.00",
        "rows": "AB",
        "cols": 10,
    }
    payload.update(overrides)
    return client.post("/events/", json=payload, headers={"authorization": token})


# ── health ────────────────────────────────────────────────────────────────────
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "event-service"


# ── list events ───────────────────────────────────────────────────────────────
def test_list_events_empty(client):
    r = client.get("/events/")
    assert r.status_code == 200
    assert r.json() == []


def test_list_events_returns_active_only(client):
    _create_event(client)
    _create_event(client, name="Cancelled Event")
    # cancel the second one
    events = client.get("/events/").json()
    assert len(events) == 2
    client.patch(f"/events/{events[1]['id']}", json={"status": "cancelled"}, headers={"authorization": ADMIN_TOKEN})
    r = client.get("/events/")
    assert len(r.json()) == 1
    assert r.json()[0]["name"] == "Test Event"


# ── get single event ──────────────────────────────────────────────────────────
def test_get_event_success(client):
    created = _create_event(client).json()
    r = client.get(f"/events/{created['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Test Event"


def test_get_event_not_found(client):
    r = client.get("/events/9999")
    assert r.status_code == 404


# ── create event ──────────────────────────────────────────────────────────────
def test_create_event_success(client):
    r = _create_event(client)
    assert r.status_code == 201
    data = r.json()
    assert data["total_seats"] == 20
    assert data["available_seats"] == 20
    assert data["status"] == "active"


def test_create_event_generates_seats(client):
    event = _create_event(client).json()
    seats = client.get(f"/events/{event['id']}/seats").json()
    assert len(seats) == 20
    labels = {s["seat_label"] for s in seats}
    assert "A1" in labels and "B10" in labels


def test_create_event_requires_admin(client):
    r = _create_event(client, token=USER_TOKEN)
    assert r.status_code == 403


def test_create_event_requires_auth(client):
    r = client.post("/events/", json={
        "name": "X", "date": "2025-12-01", "time": "10:00:00",
        "venue": "V", "city": "C", "total_seats": 10, "price": "50",
        "rows": "A", "cols": 10,
    })
    assert r.status_code == 422  # missing authorization header


def test_create_event_layout_mismatch(client):
    # rows="AB" cols=10 → 20 seats, but total_seats=15
    r = _create_event(client, total_seats=15, rows="AB", cols=10)
    assert r.status_code == 422


def test_create_event_invalid_price(client):
    r = _create_event(client, price="-10")
    assert r.status_code == 422


def test_create_event_invalid_seats(client):
    r = _create_event(client, total_seats=0, rows="", cols=0)
    assert r.status_code == 422


# ── update event status ───────────────────────────────────────────────────────
def test_update_status_success(client):
    event = _create_event(client).json()
    r = client.patch(
        f"/events/{event['id']}",
        json={"status": "cancelled"},
        headers={"authorization": ADMIN_TOKEN},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_update_status_invalid_value(client):
    event = _create_event(client).json()
    r = client.patch(
        f"/events/{event['id']}",
        json={"status": "deleted"},
        headers={"authorization": ADMIN_TOKEN},
    )
    assert r.status_code == 422


def test_update_status_requires_admin(client):
    event = _create_event(client).json()
    r = client.patch(
        f"/events/{event['id']}",
        json={"status": "cancelled"},
        headers={"authorization": USER_TOKEN},
    )
    assert r.status_code == 403


def test_update_status_not_found(client):
    r = client.patch(
        "/events/9999",
        json={"status": "cancelled"},
        headers={"authorization": ADMIN_TOKEN},
    )
    assert r.status_code == 404


# ── seat queries ──────────────────────────────────────────────────────────────
def test_get_seats_all(client):
    event = _create_event(client).json()
    r = client.get(f"/events/{event['id']}/seats")
    assert r.status_code == 200
    assert len(r.json()) == 20


def test_get_available_seats(client):
    event = _create_event(client).json()
    r = client.get(f"/events/{event['id']}/seats/available")
    assert r.status_code == 200
    assert len(r.json()) == 20
    assert all(s["status"] == "available" for s in r.json())


def test_get_seats_event_not_found(client):
    r = client.get("/events/9999/seats")
    assert r.status_code == 404


def test_get_available_seats_event_not_found(client):
    r = client.get("/events/9999/seats/available")
    assert r.status_code == 404


# ── JWT edge cases ────────────────────────────────────────────────────────────
def test_expired_token_rejected(client):
    expired = f"Bearer {_make_token('admin', 99, expired=True)}"
    r = _create_event(client, token=expired)
    assert r.status_code == 401


def test_invalid_token_rejected(client):
    r = _create_event(client, token="Bearer not.a.token")
    assert r.status_code == 401


def test_wrong_secret_rejected(client):
    bad_token = _jwt.encode({"sub": "99", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-secret", algorithm="HS256")
    r = _create_event(client, token=f"Bearer {bad_token}")
    assert r.status_code == 401
