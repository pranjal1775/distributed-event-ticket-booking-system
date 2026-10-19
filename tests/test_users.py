"""
User Service Tests
==================
Uses FastAPI TestClient with an in-memory SQLite database.
No running PostgreSQL required.

SQLite in-memory note:
  Each new connection to sqlite:///:memory: gets a fresh empty database.
  We use a single shared connection and bind all sessions to it so that
  create_all and the test sessions all see the same data.

Tests:
  1.  Health endpoint
  2.  Successful registration
  3.  Duplicate email registration
  4.  Short password rejected
  5.  Empty full_name rejected
  6.  Successful login
  7.  Wrong password rejected
  8.  Non-existent email rejected
  9.  JWT signature validation
  10. JWT expiry validation
  11. Get own profile (/users/me)
  12. Get user by ID
  13. Admin-only list users — forbidden for regular user
  14. Admin-only list users — allowed for admin
  15. Role field in token payload
"""

import os
import sys
import time
import warnings

# ── point to service source ───────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "user-service"))

# Each service uses a top-level package named `app`; isolate it when pytest
# collects multiple service suites in the same interpreter.
for _module_name in tuple(sys.modules):
    if _module_name == "app" or _module_name.startswith("app."):
        del sys.modules[_module_name]

# ── env vars BEFORE any app import ───────────────────────────────────────────
os.environ["JWT_SECRET"]         = "test-secret-for-unit-tests-only-32chars"
os.environ["JWT_ALGORITHM"]      = "HS256"
os.environ["JWT_EXPIRY_MINUTES"] = "60"
os.environ["POSTGRES_HOST"]      = "localhost"

# ── single shared SQLite connection ──────────────────────────────────────────
# SQLite :memory: gives each connection its own empty DB.
# Binding all sessions to ONE connection ensures create_all and queries
# share the same in-memory state.
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_conn   = _engine.connect()          # keep this connection alive for the whole session

# Patch db module BEFORE importing app
import app.database as db_module

# Create a session factory bound to the single connection
_Session = sessionmaker(bind=_conn, autocommit=False, autoflush=False)
db_module.engine       = _engine
db_module.SessionLocal = _Session

# ── import app after patching ─────────────────────────────────────────────────
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, get_db
from app.models import User  # noqa: F401 — registers User with Base.metadata

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from app.auth import hash_password, create_access_token

# Create all tables on the shared connection
Base.metadata.create_all(bind=_conn)


def _override_get_db():
    db = _Session()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_users():
    """Delete all rows before each test."""
    _conn.execute(text("DELETE FROM users"))
    _conn.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    resp = client.post("/users/register", json={
        "email":     "alice@example.com",
        "password":  "password123",
        "full_name": "Alice Test",
    })
    assert resp.status_code == 201, resp.text
    return resp.json(), "password123"


@pytest.fixture
def admin_token():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hashed = hash_password("adminpass")
    _conn.execute(
        text("INSERT INTO users (email, hashed_password, full_name, role) VALUES (:e,:h,:f,:r)"),
        {"e": "admin@example.com", "h": hashed, "f": "Admin User", "r": "admin"},
    )
    _conn.commit()
    row = _conn.execute(text("SELECT id FROM users WHERE email='admin@example.com'")).fetchone()
    return create_access_token(row[0], "admin")


# ── tests ─────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["service"] == "user-service"


def test_register_success(client):
    r = client.post("/users/register", json={
        "email":     "bob@example.com",
        "password":  "securepass",
        "full_name": "Bob Smith",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "bob@example.com"
    assert data["user"]["role"]  == "user"
    assert "hashed_password" not in data["user"]


def test_register_duplicate_email(client, registered_user):
    r = client.post("/users/register", json={
        "email":     "alice@example.com",
        "password":  "anotherpass",
        "full_name": "Alice Duplicate",
    })
    assert r.status_code == 409
    assert "already registered" in r.json()["detail"].lower()


def test_register_short_password(client):
    r = client.post("/users/register", json={
        "email":     "short@example.com",
        "password":  "abc",
        "full_name": "Short Pass",
    })
    assert r.status_code == 422


def test_register_seven_character_password_rejected(client):
    r = client.post("/users/register", json={"email":"seven@example.com", "password":"1234567", "full_name":"Seven"})
    assert r.status_code == 422


def test_password_is_hashed(client):
    client.post("/users/register", json={"email":"hash@example.com", "password":"password123", "full_name":"Hash"})
    row = _conn.execute(text("SELECT hashed_password FROM users WHERE email='hash@example.com'")).fetchone()
    assert row and row[0] != "password123" and row[0].startswith("$2")


def test_malformed_bearer_header_rejected(client):
    r = client.get("/users/me", headers={"authorization":"Bearer   "})
    assert r.status_code == 401


def test_register_empty_full_name(client):
    r = client.post("/users/register", json={
        "email":     "noname@example.com",
        "password":  "validpass",
        "full_name": "   ",
    })
    assert r.status_code == 422


def test_login_success(client, registered_user):
    _, password = registered_user
    r = client.post("/users/login", json={
        "email":    "alice@example.com",
        "password": password,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == "alice@example.com"


def test_login_wrong_password(client, registered_user):
    r = client.post("/users/login", json={
        "email":    "alice@example.com",
        "password": "wrongpassword",
    })
    assert r.status_code == 401
    assert "invalid" in r.json()["detail"].lower()


def test_login_nonexistent_email(client):
    r = client.post("/users/login", json={
        "email":    "nobody@example.com",
        "password": "somepass",
    })
    assert r.status_code == 401


def test_get_me(client, registered_user):
    user_data, _ = registered_user
    token = user_data["access_token"]
    r = client.get("/users/me", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "alice@example.com"


def test_get_me_no_token(client):
    r = client.get("/users/me")
    assert r.status_code in (401, 422)


def test_get_me_invalid_token(client):
    r = client.get("/users/me", headers={"authorization": "Bearer invalidtoken"})
    assert r.status_code == 401


def test_jwt_wrong_signature(client, registered_user):
    from jose import jwt as jose_jwt
    bad_token = jose_jwt.encode(
        {"sub": "1", "role": "user", "exp": int(time.time()) + 3600},
        "completely-wrong-secret",
        algorithm="HS256",
    )
    r = client.get("/users/me", headers={"authorization": f"Bearer {bad_token}"})
    assert r.status_code == 401


def test_jwt_expired_token(client, registered_user):
    from jose import jwt as jose_jwt
    expired_token = jose_jwt.encode(
        {"sub": "1", "role": "user", "exp": int(time.time()) - 10},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    r = client.get("/users/me", headers={"authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_get_user_by_id(client, registered_user):
    user_data, _ = registered_user
    token   = user_data["access_token"]
    user_id = user_data["user"]["id"]
    r = client.get(f"/users/{user_id}", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == user_id


def test_get_user_by_id_not_found(client, registered_user):
    user_data, _ = registered_user
    token = user_data["access_token"]
    r = client.get("/users/99999", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_list_users_forbidden_for_regular_user(client, registered_user):
    user_data, _ = registered_user
    token = user_data["access_token"]
    r = client.get("/users/", headers={"authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_list_users_allowed_for_admin(client, admin_token):
    r = client.get("/users/", headers={"authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_token_payload_contains_role(client):
    from jose import jwt as jose_jwt
    r = client.post("/users/register", json={
        "email":     "rolecheck@example.com",
        "password":  "testpass",
        "full_name": "Role Check",
    })
    assert r.status_code == 201
    token   = r.json()["access_token"]
    payload = jose_jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
    assert "sub"  in payload
    assert "role" in payload
    assert payload["role"] == "user"
