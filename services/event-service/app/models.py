from sqlalchemy import Column, Integer, String, Text, Date, Time, Numeric, DateTime, ForeignKey, func
from .database import Base


class Event(Base):
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String(255), nullable=False)
    description     = Column(Text)
    date            = Column(Date, nullable=False)
    time            = Column(Time, nullable=False)
    venue           = Column(String(255), nullable=False)
    city            = Column(String(100), nullable=False)
    total_seats     = Column(Integer, nullable=False)
    available_seats = Column(Integer, nullable=False)
    price           = Column(Numeric(10, 2), nullable=False)
    status          = Column(String(20), nullable=False, default="active")
    created_at      = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)


class Seat(Base):
    __tablename__ = "seats"

    id         = Column(Integer, primary_key=True, index=True)
    event_id   = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    seat_label = Column(String(10), nullable=False)
    status     = Column(String(20), nullable=False, default="available")
