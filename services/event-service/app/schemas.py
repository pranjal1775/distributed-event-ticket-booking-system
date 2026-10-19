from datetime import date, time, datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, field_validator


class EventCreate(BaseModel):
    name:        str
    description: Optional[str] = None
    date:        date
    time:        time
    venue:       str
    city:        str
    total_seats: int
    price:       Decimal
    # seat layout: rows is a string like "ABCD", cols is seats per row
    rows:        str   = "ABCD"
    cols:        int   = 10

    @field_validator("total_seats")
    @classmethod
    def seats_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("total_seats must be positive")
        return v

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("price must be non-negative")
        return v

    @field_validator("rows")
    @classmethod
    def rows_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("rows must not be empty")
        return v.upper()


class EventStatusUpdate(BaseModel):
    status: Literal["active", "cancelled", "completed"]


class EventResponse(BaseModel):
    id:              int
    name:            str
    description:     Optional[str]
    date:            date
    time:            time
    venue:           str
    city:            str
    total_seats:     int
    available_seats: int
    price:           Decimal
    status:          str
    created_at:      datetime

    model_config = {"from_attributes": True}


class SeatResponse(BaseModel):
    id:         int
    event_id:   int
    seat_label: str
    status:     str

    model_config = {"from_attributes": True}
