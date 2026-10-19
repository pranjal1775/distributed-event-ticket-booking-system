from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, func
from .database import Base


class Event(Base):
    """Read-only view of events table — owned by event-service."""
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True)
    available_seats = Column(Integer, nullable=False)
    price           = Column(Numeric(10, 2), nullable=False)
    status          = Column(String(20), nullable=False)


class Seat(Base):
    """Read/write access to seats table — owned by event-service."""
    __tablename__ = "seats"

    id         = Column(Integer, primary_key=True)
    event_id   = Column(Integer, ForeignKey("events.id"), nullable=False)
    seat_label = Column(String(10), nullable=False)
    status     = Column(String(20), nullable=False, default="available")


class Booking(Base):
    __tablename__ = "bookings"

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, nullable=False)
    event_id       = Column(Integer, nullable=False)
    total_amount   = Column(Numeric(10, 2), nullable=False)
    payment_status = Column(String(20), nullable=False, default="pending")
    booking_status = Column(String(20), nullable=False, default="pending")
    logical_clock  = Column(Integer)
    created_at     = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class BookingItem(Base):
    __tablename__ = "booking_items"

    id         = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False)
    seat_id    = Column(Integer, ForeignKey("seats.id"), nullable=False)
    seat_label = Column(String(10), nullable=False)
