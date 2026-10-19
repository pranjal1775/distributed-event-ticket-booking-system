from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NotificationCreate(BaseModel):
    user_id:    int
    booking_id: int
    message:    str


class NotificationResponse(BaseModel):
    id:            int
    user_id:       int
    booking_id:    int
    message:       str
    status:        str
    logical_clock: Optional[int]
    created_at:    datetime

    model_config = {"from_attributes": True}
