from datetime import datetime
from decimal import Decimal
from typing import List
from pydantic import BaseModel, field_validator


class BookingRequest(BaseModel):
    event_id:  int
    seat_ids:  List[int]

    @field_validator("seat_ids")
    @classmethod
    def seats_not_empty(cls, v: List[int]) -> List[int]:
        if not v:
            raise ValueError("seat_ids must not be empty")
        if len(v) != len(set(v)):
            raise ValueError("seat_ids must not contain duplicates")
        return v


class BookingItemResponse(BaseModel):
    id:         int
    seat_id:    int
    seat_label: str

    model_config = {"from_attributes": True}


class BookingResponse(BaseModel):
    id:             int
    user_id:        int
    event_id:       int
    total_amount:   Decimal
    payment_status: str
    booking_status: str
    logical_clock:  int
    created_at:     datetime
    items:          List[BookingItemResponse] = []

    model_config = {"from_attributes": True}
