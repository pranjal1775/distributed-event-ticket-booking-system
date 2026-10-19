import logging
from typing import List

from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from .database import get_db
from .models import Notification
from .schemas import NotificationCreate, NotificationResponse
from .auth import verify_internal_token, decode_user_token

logger = logging.getLogger(__name__)
router = APIRouter()

# Lamport logical clock — mirrors booking-service clock for ordering demo
_logical_clock: int = 0


def _next_clock() -> int:
    global _logical_clock
    _logical_clock += 1
    return _logical_clock


@router.post("/", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED)
def create_notification(
    body: NotificationCreate,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """Called internally by booking-service after a confirmed booking."""
    verify_internal_token(authorization)

    notification = Notification(
        user_id       = body.user_id,
        booking_id    = body.booking_id,
        message       = body.message,
        status        = "sent",
        logical_clock = _next_clock(),
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)

    logger.info(
        "[notification-service] Stored notification id=%d user=%d booking=%d clock=%d",
        notification.id, body.user_id, body.booking_id, notification.logical_clock,
    )
    return notification


@router.get("/my", response_model=List[NotificationResponse])
def my_notifications(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    """Returns all notifications for the authenticated user."""
    payload = decode_user_token(authorization)
    user_id = int(payload["sub"])
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.id)
        .all()
    )
