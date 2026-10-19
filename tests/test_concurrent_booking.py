"""
tests/test_concurrent_booking.py

Concurrent booking tests — verifies that the booking logic prevents
double-booking when multiple threads race for the same seat(s).

SQLite does not support SELECT FOR UPDATE. We model its effect by
overriding get_db with a mutex-protected session factory: only one
thread holds the DB lock at a time, exactly as SELECT FOR UPDATE
serialises conflicting transactions on PostgreSQL.

The UNIQUE(seat_id) constraint on booking_items is the final safety
net and is enforced by SQLite as well.

Run from project root:
    pytest tests/test_concurrent_booking.py -v
"""
import os
import sys
import threading
import pytest

# ── env vars before any app import ──────────────────────────────────────────
os.environ["JWT_SECRET"]               = "test-secret-key"
os.environ["JWT_ALGORITHM"]            = "HS256"
os.environ["JWT_EXPIRY_MINUTES"]       = "60"
os.environ["PAYMENT_MODE"]             = "success"
os.environ["NOTIFICATION_SERVICE_URL"] = "http://localhost:9999"

# ── shared in-memory SQLite engine ───────────────────────────────────────────
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_conn        = _engine.connect()
_TestSession = sessionmaker(bind=_conn, autocommit=False, autoflush=False)

# Mutex that serialises all DB sessions — models SELECT FOR UPDATE on SQLite
_db_lock = threading.Lock()

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

# Override get_db to acquire the mutex for the full duration of each request
import app.routes as _routes
import app.main   as _main

def _locked_get_db():
    with _db_lock:
        db = _TestSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

# Patch the dependency on the router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

@asynccontextmanager
async def _lifespan(application: FastAPI):
    yield

_app = FastAPI(lifespan=_lifespan)
_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from fastapi import Depends
_routes.router.dependencies.clear()
_app.include_router(_routes.router, prefix="/bookings")

# Override the get_db dependency on every route
from app.database import get_db as _orig_get_db
_app.dependency_overrides[_orig_get_db] = _locked_get_db

@_app.get("/health")
def health():
    return {"status": "ok", "service": "booking-service"}

from fastapi.testclient import TestClient

# ── JWT helpers ───────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
from jose import jwt as _jwt

def _token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=60)
    return _jwt.encode({"sub": str(user_id), "role": "user", "exp": exp}, "test-secret-key", algorithm="HS256")

def _auth(user_id: int) -> dict:
    return {"authorization": f"Bearer {_token(user_id)}"}

# ── seed helpers ──────────────────────────────────────────────────────────────

def _seed_event(available: int = 20) -> int:
    r = _conn.execute(Event.__table__.insert().values(
        available_seats=available, price=100.0, status="active"
    ))
    _conn.commit()
    return r.inserted_primary_key[0]

def _seed_seats(event_id: int, count: int) -> list:
    ids = []
    for i in range(1, count + 1):
        r = _conn.execute(Seat.__table__.insert().values(
            event_id=event_id, seat_label=f"A{i}", status="available"
        ))
        _conn.commit()
        ids.append(r.inserted_primary_key[0])
    return ids

def _get_seat_status(seat_id: int) -> str:
    return _conn.execute(
        Seat.__table__.select().where(Seat.id == seat_id)
    ).fetchone().status

def _get_available_seats(event_id: int) -> int:
    return _conn.execute(
        Event.__table__.select().where(Event.id == event_id)
    ).fetchone().available_seats

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    _conn.execute(BookingItem.__table__.delete())
    _conn.execute(Booking.__table__.delete())
    _conn.execute(Seat.__table__.delete())
    _conn.execute(Event.__table__.delete())
    _conn.commit()
    with _routes._clock_lock:
        _routes._logical_clock = 0
    yield

# ── concurrent helper ─────────────────────────────────────────────────────────

def _run_concurrent(payloads: list, auth_ids: list) -> list:
    """
    Fire len(payloads) booking requests concurrently using threads.
    A Barrier synchronises all threads to start at the same moment.
    The _db_lock inside _locked_get_db serialises actual DB access,
    modelling SELECT FOR UPDATE row-level locking.
    Returns list of HTTP status codes indexed by thread.
    """
    n       = len(payloads)
    results = [None] * n
    barrier = threading.Barrier(n)

    def _book(idx: int):
        with TestClient(_app, raise_server_exceptions=False) as client:
            barrier.wait()
            r = client.post(
                "/bookings/",
                json=payloads[idx],
                headers=_auth(auth_ids[idx]),
            )
            results[idx] = r.status_code

    threads = [threading.Thread(target=_book, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results


# ── tests ─────────────────────────────────────────────────────────────────────

def test_10_threads_same_seat_exactly_one_succeeds():
    """
    10 users race for the same single seat.
    Exactly 1 must get 201; the other 9 must get 409.
    The seat must end up in 'booked' state.
    """
    n       = 10
    eid     = _seed_event(available=n)
    sids    = _seed_seats(eid, count=1)
    seat_id = sids[0]

    payloads = [{"event_id": eid, "seat_ids": [seat_id]}] * n
    auth_ids = list(range(1, n + 1))

    statuses = _run_concurrent(payloads, auth_ids)

    successes = statuses.count(201)
    conflicts = statuses.count(409)

    assert successes == 1,     f"Expected 1 success, got {successes}. Statuses: {statuses}"
    assert conflicts == n - 1, f"Expected {n-1} conflicts, got {conflicts}. Statuses: {statuses}"
    assert _get_seat_status(seat_id) == "booked"


def test_10_threads_unique_seats_all_succeed():
    """
    10 users each race for a different seat — all 10 must succeed.
    """
    n    = 10
    eid  = _seed_event(available=n)
    sids = _seed_seats(eid, count=n)

    payloads = [{"event_id": eid, "seat_ids": [sids[i]]} for i in range(n)]
    auth_ids = list(range(1, n + 1))

    statuses  = _run_concurrent(payloads, auth_ids)
    successes = statuses.count(201)

    assert successes == n, f"Expected {n} successes, got {successes}. Statuses: {statuses}"
    for sid in sids:
        assert _get_seat_status(sid) == "booked"


def test_available_seats_accurate_after_concurrent_bookings():
    """
    After N concurrent single-seat bookings on N distinct seats,
    available_seats must equal original_count - N.
    """
    n       = 5
    initial = 10
    eid     = _seed_event(available=initial)
    sids    = _seed_seats(eid, count=n)

    payloads = [{"event_id": eid, "seat_ids": [sids[i]]} for i in range(n)]
    auth_ids = list(range(1, n + 1))

    statuses  = _run_concurrent(payloads, auth_ids)
    successes = statuses.count(201)

    remaining = _get_available_seats(eid)
    assert remaining == initial - successes, (
        f"available_seats={remaining}, expected {initial - successes}"
    )


def test_overlapping_seat_sets_no_double_booking():
    """
    Thread A wants seats [0,1], Thread B wants seats [1,2].
    Seat 1 is contested — it must appear in exactly one booking_items row.
    """
    eid  = _seed_event(available=10)
    sids = _seed_seats(eid, count=3)

    payloads = [
        {"event_id": eid, "seat_ids": [sids[0], sids[1]]},
        {"event_id": eid, "seat_ids": [sids[1], sids[2]]},
    ]
    auth_ids = [1, 2]

    statuses = _run_concurrent(payloads, auth_ids)

    assert 201 in statuses, f"Expected at least one success. Statuses: {statuses}"

    contested = _conn.execute(
        BookingItem.__table__.select().where(BookingItem.seat_id == sids[1])
    ).fetchall()

    assert len(contested) == 1, (
        f"Seat {sids[1]} booked {len(contested)} times — double-booking detected!"
    )


def test_logical_clocks_unique_across_concurrent_bookings():
    """
    All confirmed bookings must have distinct logical_clock values.
    """
    n    = 8
    eid  = _seed_event(available=n)
    sids = _seed_seats(eid, count=n)

    payloads = [{"event_id": eid, "seat_ids": [sids[i]]} for i in range(n)]
    auth_ids = list(range(1, n + 1))

    _run_concurrent(payloads, auth_ids)

    rows   = _conn.execute(Booking.__table__.select()).fetchall()
    clocks = [r.logical_clock for r in rows if r.logical_clock is not None]

    assert len(clocks) == len(set(clocks)), (
        f"Duplicate logical_clock values: {sorted(clocks)}"
    )


def test_no_orphaned_booking_rows_on_seat_conflict():
    """
    When a booking fails due to seat conflict, no Booking row must remain
    (full rollback). Exactly 1 booking row for 1 seat contested by N threads.
    """
    n       = 5
    eid     = _seed_event(available=n)
    sids    = _seed_seats(eid, count=1)
    seat_id = sids[0]

    payloads = [{"event_id": eid, "seat_ids": [seat_id]}] * n
    auth_ids = list(range(1, n + 1))

    _run_concurrent(payloads, auth_ids)

    booking_count = len(_conn.execute(Booking.__table__.select()).fetchall())
    assert booking_count == 1, (
        f"Expected exactly 1 booking row, found {booking_count} — orphaned rows detected"
    )
