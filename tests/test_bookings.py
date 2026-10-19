"""
tests/test_bookings.py

Run from project root:
    pytest tests/test_bookings.py -v
"""
import os
import sys
import pytest

# ── env vars before any app import ──────────────────────────────────────────
os.environ["JWT_SECRET"]          = "test-secret-key"
os.environ["JWT_ALGORITHM"]       = "HS256"
os.environ["JWT_EXPIRY_MINUTES"]  = "60"
os.environ["PAYMENT_MODE"]        = "success"   # deterministic
os.environ["NOTIFICATION_SERVICE_URL"] = "http://localhost:9999"  # unreachable — tests fire-and-forget

# ── inject SQLite engine before app import ───────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_conn   = _engine.connect()
_TestSession = sessionmaker(bind=_conn, autocommit=False, autoflush=False)

for _module_name in tuple(sys.modules):
    if _module_name == "app" or _module_name.startswith("app."):
        del sys.modules[_module_name]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "booking-service"))
import app.database as _db_module

_db_module.engine       = _engine
_db_module.SessionLocal = _TestSession

from app.models import Booking, BookingItem, Event, Seat
from app.database import Base
Base.metadata.create_all(bind=_conn)

from app.main import app
import app.routes as _booking_routes
from fastapi.testclient import TestClient

# ── JWT helpers ──────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
from jose import jwt as _jwt

def _token(user_id: int = 1, role: str = "user", expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 60)
    return _jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, "test-secret-key", algorithm="HS256")

def _auth(user_id: int = 1, role: str = "user") -> dict:
    return {"authorization": f"Bearer {_token(user_id, role)}"}

# ── seed helpers ─────────────────────────────────────────────────────────────

def _seed_event(price: float = 100.0, status: str = "active") -> int:
    """Insert a minimal event row and return its id."""
    result = _conn.execute(
        Event.__table__.insert().values(
            available_seats=10, price=price, status=status
        )
    )
    _conn.commit()
    return result.inserted_primary_key[0]


def _seed_seats(event_id: int, count: int = 5) -> list[int]:
    """Insert `count` available seats for the event and return their ids."""
    ids = []
    for i in range(1, count + 1):
        r = _conn.execute(
            Seat.__table__.insert().values(
                event_id=event_id, seat_label=f"A{i}", status="available"
            )
        )
        _conn.commit()
        ids.append(r.inserted_primary_key[0])
    return ids


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    _conn.execute(BookingItem.__table__.delete())
    _conn.execute(Booking.__table__.delete())
    _conn.execute(Seat.__table__.delete())
    _conn.execute(Event.__table__.delete())
    _conn.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def event_and_seats():
    eid   = _seed_event()
    sids  = _seed_seats(eid, count=5)
    return eid, sids


# ── health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "booking-service"


# ── create booking — happy path ───────────────────────────────────────────────

def test_create_booking_success(client, event_and_seats):
    eid, sids = event_and_seats
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": sids[:2]}, headers=_auth())
    assert r.status_code == 201
    data = r.json()
    assert data["booking_status"] == "confirmed"
    assert data["payment_status"] == "paid"
    assert data["user_id"] == 1
    assert data["event_id"] == eid
    assert float(data["total_amount"]) == 200.0   # 2 seats × ₹100
    assert len(data["items"]) == 2
    assert data["logical_clock"] >= 1


def test_create_booking_seats_marked_booked(client, event_and_seats):
    eid, sids = event_and_seats
    client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth())
    seat = _conn.execute(Seat.__table__.select().where(Seat.id == sids[0])).fetchone()
    assert seat.status == "booked"


def test_create_booking_decrements_available_seats(client, event_and_seats):
    eid, sids = event_and_seats
    client.post("/bookings/", json={"event_id": eid, "seat_ids": sids[:3]}, headers=_auth())
    event = _conn.execute(Event.__table__.select().where(Event.id == eid)).fetchone()
    assert event.available_seats == 7   # 10 - 3


def test_logical_clock_increments(client, event_and_seats):
    eid, sids = event_and_seats
    r1 = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth(1))
    r2 = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[1]]}, headers=_auth(2))
    assert r2.json()["logical_clock"] > r1.json()["logical_clock"]


# ── create booking — validation errors ───────────────────────────────────────

def test_create_booking_empty_seat_ids(client, event_and_seats):
    eid, _ = event_and_seats
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": []}, headers=_auth())
    assert r.status_code == 422


def test_create_booking_duplicate_seat_ids(client, event_and_seats):
    eid, sids = event_and_seats
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0], sids[0]]}, headers=_auth())
    assert r.status_code == 422


def test_create_booking_event_not_found(client):
    r = client.post("/bookings/", json={"event_id": 9999, "seat_ids": [1]}, headers=_auth())
    assert r.status_code == 404


def test_create_booking_inactive_event(client):
    eid   = _seed_event(status="cancelled")
    sids  = _seed_seats(eid, count=2)
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": sids[:1]}, headers=_auth())
    assert r.status_code == 409


def test_create_booking_seat_not_found(client, event_and_seats):
    eid, _ = event_and_seats
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": [99999]}, headers=_auth())
    assert r.status_code == 404


def test_create_booking_seat_wrong_event(client):
    eid1  = _seed_event()
    eid2  = _seed_event()
    sids1 = _seed_seats(eid1, count=2)
    sids2 = _seed_seats(eid2, count=2)
    # try to book a seat from event2 against event1
    r = client.post("/bookings/", json={"event_id": eid1, "seat_ids": [sids2[0]]}, headers=_auth())
    assert r.status_code == 409


def test_create_booking_seat_already_booked(client, event_and_seats):
    eid, sids = event_and_seats
    client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth())
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth(2))
    assert r.status_code == 409


# ── payment failure ───────────────────────────────────────────────────────────

def test_payment_failure_returns_402(client, event_and_seats, monkeypatch):
    eid, sids = event_and_seats
    monkeypatch.setattr(_booking_routes, "process_payment", lambda amount: False)
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth())
    assert r.status_code == 402


def test_payment_failure_seats_remain_available(client, event_and_seats, monkeypatch):
    eid, sids = event_and_seats
    monkeypatch.setattr(_booking_routes, "process_payment", lambda amount: False)
    client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth())
    seat = _conn.execute(Seat.__table__.select().where(Seat.id == sids[0])).fetchone()
    assert seat.status == "available"


@pytest.mark.parametrize("failure", ["connection", "http_status"])
def test_notification_failure_does_not_undo_booking(client, event_and_seats, monkeypatch, failure):
    eid, sids = event_and_seats

    if failure == "connection":
        def fail_request(*args, **kwargs):
            raise _booking_routes.httpx.ConnectError("notification service unavailable")
    else:
        def fail_request(*args, **kwargs):
            return _booking_routes.httpx.Response(
                503,
                request=_booking_routes.httpx.Request("POST", "http://notification-service/notifications/"),
            )

    monkeypatch.setattr(_booking_routes.httpx, "post", fail_request)
    response = client.post(
        "/bookings/",
        json={"event_id": eid, "seat_ids": [sids[0]]},
        headers=_auth(),
    )

    assert response.status_code == 201, response.text
    seat = _conn.execute(Seat.__table__.select().where(Seat.id == sids[0])).fetchone()
    event = _conn.execute(Event.__table__.select().where(Event.id == eid)).fetchone()
    assert seat.status == "booked"
    assert event.available_seats == 9


# ── get booking ───────────────────────────────────────────────────────────────

def test_get_booking_success(client, event_and_seats):
    eid, sids = event_and_seats
    created = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth()).json()
    r = client.get(f"/bookings/{created['id']}", headers=_auth())
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_booking_not_found(client):
    r = client.get("/bookings/9999", headers=_auth())
    assert r.status_code == 404


def test_get_booking_other_user_forbidden(client, event_and_seats):
    eid, sids = event_and_seats
    created = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth(1)).json()
    r = client.get(f"/bookings/{created['id']}", headers=_auth(2))  # different user
    assert r.status_code == 403


# ── my bookings ───────────────────────────────────────────────────────────────

def test_my_bookings_empty(client):
    r = client.get("/bookings/my", headers=_auth())
    assert r.status_code == 200
    assert r.json() == []


def test_my_bookings_returns_own_only(client, event_and_seats):
    eid, sids = event_and_seats
    client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]}, headers=_auth(1))
    client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[1]]}, headers=_auth(2))
    r = client.get("/bookings/my", headers=_auth(1))
    assert len(r.json()) == 1
    assert r.json()[0]["user_id"] == 1


# ── auth edge cases ───────────────────────────────────────────────────────────

def test_expired_token_rejected(client, event_and_seats):
    eid, sids = event_and_seats
    r = client.post(
        "/bookings/",
        json={"event_id": eid, "seat_ids": [sids[0]]},
        headers={"authorization": f"Bearer {_token(expired=True)}"},
    )
    assert r.status_code == 401


def test_invalid_token_rejected(client, event_and_seats):
    eid, sids = event_and_seats
    r = client.post(
        "/bookings/",
        json={"event_id": eid, "seat_ids": [sids[0]]},
        headers={"authorization": "Bearer not.a.real.token"},
    )
    assert r.status_code == 401


def test_missing_auth_header(client, event_and_seats):
    eid, sids = event_and_seats
    r = client.post("/bookings/", json={"event_id": eid, "seat_ids": [sids[0]]})
    assert r.status_code == 422  # missing required header
