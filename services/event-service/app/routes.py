import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .database import get_db
from .models import Event, Seat
from .schemas import EventCreate, EventStatusUpdate, EventResponse, SeatResponse
from .auth import decode_token, get_token_from_header

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------- helpers ----------

def _require_admin(authorization: str) -> dict:
    payload = decode_token(get_token_from_header(authorization))
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return payload


def _get_event_or_404(event_id: int, db: Session) -> Event:
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _generate_seats(event_id: int, rows: str, cols: int) -> List[Seat]:
    """Generate seat rows like A1..A10, B1..B10, etc."""
    seats = []
    for row in rows:
        for col in range(1, cols + 1):
            seats.append(Seat(event_id=event_id, seat_label=f"{row}{col}"))
    return seats


# ---------- public endpoints ----------

@router.get("/", response_model=List[EventResponse])
def list_events(db: Session = Depends(get_db)):
    return db.query(Event).filter(Event.status == "active").order_by(Event.date).all()


@router.get("/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    return _get_event_or_404(event_id, db)


@router.get("/{event_id}/seats", response_model=List[SeatResponse])
def get_seats(event_id: int, db: Session = Depends(get_db)):
    _get_event_or_404(event_id, db)
    return db.query(Seat).filter(Seat.event_id == event_id).order_by(Seat.seat_label).all()


@router.get("/{event_id}/seats/available", response_model=List[SeatResponse])
def get_available_seats(event_id: int, db: Session = Depends(get_db)):
    _get_event_or_404(event_id, db)
    return (
        db.query(Seat)
        .filter(Seat.event_id == event_id, Seat.status == "available")
        .order_by(Seat.seat_label)
        .all()
    )


# ---------- admin endpoints ----------

@router.post("/", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    _require_admin(authorization)

    # Validate seat layout matches total_seats
    expected = len(body.rows) * body.cols
    if expected != body.total_seats:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rows×cols ({expected}) must equal total_seats ({body.total_seats})",
        )

    event = Event(
        name            = body.name,
        description     = body.description,
        date            = body.date,
        time            = body.time,
        venue           = body.venue,
        city            = body.city,
        total_seats     = body.total_seats,
        available_seats = body.total_seats,
        price           = body.price,
        status          = "active",
    )
    try:
        db.add(event)
        db.flush()  # get event.id before inserting seats
        seats = _generate_seats(event.id, body.rows, body.cols)
        db.add_all(seats)
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Event creation failed")

    logger.info("[event-service] Created event id=%d name=%s seats=%d", event.id, event.name, body.total_seats)
    return event


@router.patch("/{event_id}", response_model=EventResponse)
def update_event_status(
    event_id: int,
    body: EventStatusUpdate,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    _require_admin(authorization)
    event = _get_event_or_404(event_id, db)
    event.status = body.status
    db.commit()
    db.refresh(event)
    logger.info("[event-service] Event id=%d status → %s", event_id, body.status)
    return event
