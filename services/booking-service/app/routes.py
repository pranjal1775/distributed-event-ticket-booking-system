import logging
import os
import threading
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Booking, BookingItem, Event, Seat
from .schemas import BookingRequest, BookingResponse, BookingItemResponse
from .auth import decode_token, get_token_from_header
from .payment import process_payment

logger = logging.getLogger(__name__)
router = APIRouter()

# Lamport logical clock — shared across all requests on this process.
# In a multi-pod deployment each pod maintains its own counter; the value
# is stored per-booking in the DB so it can be compared across replicas.
_logical_clock: int = 0
_clock_lock = threading.Lock()


def _next_clock() -> int:
    global _logical_clock
    with _clock_lock:
        _logical_clock += 1
        return _logical_clock


def _current_user_id(authorization: str) -> int:
    payload = decode_token(get_token_from_header(authorization))
    return int(payload["sub"])


def _notify(user_id: int, booking_id: int, message: str) -> None:
    """Fire-and-forget POST to notification-service. Failures are logged, not raised."""
    url = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004")
    token = os.getenv("INTERNAL_SERVICE_TOKEN", "")
    try:
        response = httpx.post(
            f"{url}/notifications/",
            json={"user_id": user_id, "booking_id": booking_id, "message": message},
            headers={"authorization": f"Bearer {token}"},
            timeout=3.0,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("[booking-service] Notification failed (booking_id=%d): %s", booking_id, exc)


# ---------- endpoints ----------

@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    body: BookingRequest,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(authorization)

    # ── 1. Validate event ────────────────────────────────────────────────────
    event = db.query(Event).filter(Event.id == body.event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.status != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event is not active")

    # ── 2. Lock seats with SELECT FOR UPDATE ─────────────────────────────────
    # Rows are locked in ascending id order to prevent deadlocks between
    # concurrent requests that request overlapping seat sets.
    stmt = (
        select(Seat)
        .where(Seat.id.in_(body.seat_ids))
        .order_by(Seat.id)
        .with_for_update()
    )
    seats = db.execute(stmt).scalars().all()

    if len(seats) != len(body.seat_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more seats not found")

    # ── 3. Validate seats belong to event and are available ──────────────────
    for seat in seats:
        if seat.event_id != body.event_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Seat {seat.id} does not belong to event {body.event_id}",
            )
        if seat.status != "available":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Seat {seat.seat_label} is already booked",
            )

    # ── 4. Payment ───────────────────────────────────────────────────────────
    total = float(event.price) * len(seats)
    paid  = process_payment(total)

    if not paid:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Payment failed",
        )

    # ── 5. Commit booking ────────────────────────────────────────────────────
    clock = _next_clock()

    booking = Booking(
        user_id        = user_id,
        event_id       = body.event_id,
        total_amount   = total,
        payment_status = "paid",
        booking_status = "confirmed",
        logical_clock  = clock,
    )
    db.add(booking)
    db.flush()  # get booking.id

    items = []
    for seat in seats:
        seat.status = "booked"
        item = BookingItem(booking_id=booking.id, seat_id=seat.id, seat_label=seat.seat_label)
        db.add(item)
        items.append(item)

    event.available_seats = event.available_seats - len(seats)
    db.commit()
    db.refresh(booking)

    logger.info(
        "[booking-service] Booking confirmed id=%d user=%d event=%d seats=%s clock=%d",
        booking.id, user_id, body.event_id, [s.seat_label for s in seats], clock,
    )

    # ── 6. Fire-and-forget notification ──────────────────────────────────────
    _notify(
        user_id,
        booking.id,
        f"Booking confirmed for {len(seats)} seat(s). Total: ₹{total:.2f}",
    )

    return BookingResponse(
        id             = booking.id,
        user_id        = booking.user_id,
        event_id       = booking.event_id,
        total_amount   = booking.total_amount,
        payment_status = booking.payment_status,
        booking_status = booking.booking_status,
        logical_clock  = booking.logical_clock,
        created_at     = booking.created_at,
        items          = [BookingItemResponse.model_validate(i) for i in items],
    )


@router.get("/my", response_model=List[BookingResponse])
def my_bookings(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_id  = _current_user_id(authorization)
    bookings = db.query(Booking).filter(Booking.user_id == user_id).order_by(Booking.id).all()
    result   = []
    for b in bookings:
        items = db.query(BookingItem).filter(BookingItem.booking_id == b.id).all()
        result.append(BookingResponse(
            id             = b.id,
            user_id        = b.user_id,
            event_id       = b.event_id,
            total_amount   = b.total_amount,
            payment_status = b.payment_status,
            booking_status = b.booking_status,
            logical_clock  = b.logical_clock,
            created_at     = b.created_at,
            items          = [BookingItemResponse.model_validate(i) for i in items],
        ))
    return result


@router.get("/{booking_id}", response_model=BookingResponse)
def get_booking(
    booking_id: int,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    user_id = _current_user_id(authorization)
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    items = db.query(BookingItem).filter(BookingItem.booking_id == booking_id).all()
    return BookingResponse(
        id             = booking.id,
        user_id        = booking.user_id,
        event_id       = booking.event_id,
        total_amount   = booking.total_amount,
        payment_status = booking.payment_status,
        booking_status = booking.booking_status,
        logical_clock  = booking.logical_clock,
        created_at     = booking.created_at,
        items          = [BookingItemResponse.model_validate(i) for i in items],
    )
