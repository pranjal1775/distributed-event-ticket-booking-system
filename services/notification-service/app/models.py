from sqlalchemy import Column, Integer, String, Text, DateTime, func
from .database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id            = Column(Integer, primary_key=True, index=True)
    user_id       = Column(Integer, nullable=False, index=True)
    booking_id    = Column(Integer, nullable=False)
    message       = Column(Text, nullable=False)
    status        = Column(String(20), nullable=False, default="sent")
    logical_clock = Column(Integer)
    created_at    = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
