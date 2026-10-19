import os
from fastapi import APIRouter, Depends, Request, Response
from .auth import require_jwt
from .proxy import proxy

router = APIRouter()


def _svc(env_key: str, default: str) -> str:
    return os.getenv(env_key, default)


# ── helpers ───────────────────────────────────────────────────────────────────

def _user_url(path: str) -> str:
    return _svc("USER_SERVICE_URL", "http://user-service:8001") + path

def _event_url(path: str) -> str:
    return _svc("EVENT_SERVICE_URL", "http://event-service:8002") + path

def _booking_url(path: str) -> str:
    return _svc("BOOKING_SERVICE_URL", "http://booking-service:8003") + path

def _notif_url(path: str) -> str:
    return _svc("NOTIFICATION_SERVICE_URL", "http://notification-service:8004") + path


# ── public: user auth ─────────────────────────────────────────────────────────

@router.post("/api/users/register")
async def register(request: Request) -> Response:
    return await proxy(request, _user_url("/users/register"))

@router.post("/api/users/login")
async def login(request: Request) -> Response:
    return await proxy(request, _user_url("/users/login"))


# ── protected: user ───────────────────────────────────────────────────────────

@router.get("/api/users/me")
async def get_me(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _user_url("/users/me"))

@router.get("/api/users/{user_id}")
async def get_user(user_id: int, request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _user_url(f"/users/{user_id}"))

@router.get("/api/users/")
async def list_users(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _user_url("/users/"))


# ── public: events (read-only) ────────────────────────────────────────────────

@router.get("/api/events/")
async def list_events(request: Request) -> Response:
    return await proxy(request, _event_url("/events/"))

@router.get("/api/events/{event_id}")
async def get_event(event_id: int, request: Request) -> Response:
    return await proxy(request, _event_url(f"/events/{event_id}"))

@router.get("/api/events/{event_id}/seats")
async def get_seats(event_id: int, request: Request) -> Response:
    return await proxy(request, _event_url(f"/events/{event_id}/seats"))

@router.get("/api/events/{event_id}/seats/available")
async def get_available_seats(event_id: int, request: Request) -> Response:
    return await proxy(request, _event_url(f"/events/{event_id}/seats/available"))


# ── protected: events (write) ─────────────────────────────────────────────────

@router.post("/api/events/")
async def create_event(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _event_url("/events/"))

@router.patch("/api/events/{event_id}")
async def update_event(event_id: int, request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _event_url(f"/events/{event_id}"))


# ── protected: bookings ───────────────────────────────────────────────────────

@router.post("/api/bookings/")
async def create_booking(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _booking_url("/bookings/"))

@router.get("/api/bookings/my")
async def my_bookings(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _booking_url("/bookings/my"))

@router.get("/api/bookings/{booking_id}")
async def get_booking(booking_id: int, request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _booking_url(f"/bookings/{booking_id}"))


# ── protected: notifications ──────────────────────────────────────────────────

@router.get("/api/notifications/my")
async def my_notifications(request: Request, _: dict = Depends(require_jwt)) -> Response:
    return await proxy(request, _notif_url("/notifications/my"))
