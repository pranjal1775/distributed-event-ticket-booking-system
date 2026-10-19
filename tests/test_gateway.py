"""
tests/test_gateway.py

Run from project root:
    pytest tests/test_gateway.py -v
"""
import os
import sys
import json
import pytest
import respx
import httpx

# ── env vars before any app import ──────────────────────────────────────────
os.environ["JWT_SECRET"]              = "test-secret-key"
os.environ["JWT_ALGORITHM"]           = "HS256"
os.environ["USER_SERVICE_URL"]        = "http://user-service"
os.environ["EVENT_SERVICE_URL"]       = "http://event-service"
os.environ["BOOKING_SERVICE_URL"]     = "http://booking-service"
os.environ["NOTIFICATION_SERVICE_URL"]= "http://notification-service"
os.environ["RATE_LIMIT"]              = "1000"   # effectively disabled for tests

for _module_name in tuple(sys.modules):
    if _module_name == "app" or _module_name.startswith("app."):
        del sys.modules[_module_name]
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "gateway"))

import app.main as _gateway_main
app = _gateway_main.app
from fastapi.testclient import TestClient

# ── JWT helpers ───────────────────────────────────────────────────────────────
from datetime import datetime, timezone, timedelta
from jose import jwt as _jwt

def _token(role: str = "user", user_id: int = 1, expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 60)
    return _jwt.encode({"sub": str(user_id), "role": role, "exp": exp}, "test-secret-key", algorithm="HS256")

def _auth(role: str = "user") -> dict:
    return {"authorization": f"Bearer {_token(role)}"}

ADMIN_AUTH = _auth("admin")
USER_AUTH  = _auth("user")

# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _json_response(data: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data)


# ── health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "api-gateway"


# ── public routes: no JWT needed ──────────────────────────────────────────────

@respx.mock
def test_register_proxied(client):
    respx.post("http://user-service/users/register").mock(
        return_value=_json_response({"access_token": "tok", "token_type": "bearer", "user": {}}, 201)
    )
    r = client.post("/api/users/register", json={"email": "a@b.com", "password": "pass123", "full_name": "A"})
    assert r.status_code == 201


@respx.mock
def test_login_proxied(client):
    respx.post("http://user-service/users/login").mock(
        return_value=_json_response({"access_token": "tok", "token_type": "bearer", "user": {}})
    )
    r = client.post("/api/users/login", json={"email": "a@b.com", "password": "pass123"})
    assert r.status_code == 200


@respx.mock
def test_list_events_public(client):
    respx.get("http://event-service/events/").mock(return_value=_json_response([]))
    r = client.get("/api/events/")
    assert r.status_code == 200


@respx.mock
def test_get_event_public(client):
    respx.get("http://event-service/events/1").mock(return_value=_json_response({"id": 1}))
    r = client.get("/api/events/1")
    assert r.status_code == 200


@respx.mock
def test_get_seats_public(client):
    respx.get("http://event-service/events/1/seats").mock(return_value=_json_response([]))
    r = client.get("/api/events/1/seats")
    assert r.status_code == 200


@respx.mock
def test_get_available_seats_public(client):
    respx.get("http://event-service/events/1/seats/available").mock(return_value=_json_response([]))
    r = client.get("/api/events/1/seats/available")
    assert r.status_code == 200


# ── JWT guard: missing / invalid / expired ────────────────────────────────────

def test_protected_route_no_token(client):
    r = client.get("/api/users/me")
    assert r.status_code == 401

def test_protected_route_invalid_token(client):
    r = client.get("/api/users/me", headers={"authorization": "Bearer not.a.token"})
    assert r.status_code == 401

def test_protected_route_expired_token(client):
    r = client.get("/api/users/me", headers={"authorization": f"Bearer {_token(expired=True)}"})
    assert r.status_code == 401

def test_protected_route_wrong_secret(client):
    bad = _jwt.encode({"sub": "1", "role": "user", "exp": datetime.now(timezone.utc) + timedelta(hours=1)}, "wrong-secret", algorithm="HS256")
    r = client.get("/api/users/me", headers={"authorization": f"Bearer {bad}"})
    assert r.status_code == 401


# ── protected routes proxied correctly ───────────────────────────────────────

@respx.mock
def test_get_me_proxied(client):
    respx.get("http://user-service/users/me").mock(return_value=_json_response({"id": 1}))
    r = client.get("/api/users/me", headers=USER_AUTH)
    assert r.status_code == 200


@respx.mock
def test_get_user_proxied(client):
    respx.get("http://user-service/users/2").mock(return_value=_json_response({"id": 2}))
    r = client.get("/api/users/2", headers=USER_AUTH)
    assert r.status_code == 200


@respx.mock
def test_create_event_proxied(client):
    respx.post("http://event-service/events/").mock(return_value=_json_response({"id": 1}, 201))
    r = client.post("/api/events/", json={}, headers=ADMIN_AUTH)
    assert r.status_code == 201


@respx.mock
def test_update_event_proxied(client):
    respx.patch("http://event-service/events/1").mock(return_value=_json_response({"id": 1}))
    r = client.patch("/api/events/1", json={"status": "cancelled"}, headers=ADMIN_AUTH)
    assert r.status_code == 200


@respx.mock
def test_create_booking_proxied(client):
    respx.post("http://booking-service/bookings/").mock(return_value=_json_response({"id": 1}, 201))
    r = client.post("/api/bookings/", json={}, headers=USER_AUTH)
    assert r.status_code == 201


@respx.mock
def test_my_bookings_proxied(client):
    respx.get("http://booking-service/bookings/my").mock(return_value=_json_response([]))
    r = client.get("/api/bookings/my", headers=USER_AUTH)
    assert r.status_code == 200


@respx.mock
def test_get_booking_proxied(client):
    respx.get("http://booking-service/bookings/5").mock(return_value=_json_response({"id": 5}))
    r = client.get("/api/bookings/5", headers=USER_AUTH)
    assert r.status_code == 200


@respx.mock
def test_my_notifications_proxied(client):
    respx.get("http://notification-service/notifications/my").mock(return_value=_json_response([]))
    r = client.get("/api/notifications/my", headers=USER_AUTH)
    assert r.status_code == 200


# ── upstream error passthrough ────────────────────────────────────────────────

@respx.mock
def test_upstream_404_passed_through(client):
    respx.get("http://event-service/events/999").mock(
        return_value=httpx.Response(404, json={"detail": "Event not found"})
    )
    r = client.get("/api/events/999")
    assert r.status_code == 404


@respx.mock
def test_upstream_503_on_connect_error(client):
    respx.post("http://booking-service/bookings/").mock(side_effect=httpx.ConnectError("down"))
    r = client.post("/api/bookings/", json={}, headers=USER_AUTH)
    assert r.status_code == 503


@respx.mock
def test_upstream_504_on_timeout(client):
    respx.post("http://booking-service/bookings/").mock(side_effect=httpx.TimeoutException("slow"))
    r = client.post("/api/bookings/", json={}, headers=USER_AUTH)
    assert r.status_code == 504


# ── rate limiter ──────────────────────────────────────────────────────────────

def test_rate_limiter_blocks_after_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT", "3")
    # Reset the rate limiter state
    _gateway_main._request_log.clear()

    # Patch RATE_LIMIT used at runtime
    original = _gateway_main.RATE_LIMIT
    _gateway_main.RATE_LIMIT = 3

    try:
        with respx.mock:
            respx.get("http://event-service/events/").mock(return_value=_json_response([]))
            for _ in range(3):
                client.get("/api/events/")
            r = client.get("/api/events/")   # 4th request — should be blocked
            assert r.status_code == 429
    finally:
        _gateway_main.RATE_LIMIT = original
        _gateway_main._request_log.clear()
