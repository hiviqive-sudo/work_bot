from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Service:
    id: int
    name: str
    price: int
    duration_min: int
    is_active: int = 1


@dataclass(slots=True)
class Appointment:
    id: int
    user_id: int
    service_id: int
    service_name: str
    price: int
    duration_min: int
    appointment_date: str
    start_time: str
    end_time: str
    status: str
    comment: str | None
    username: str | None = None
    full_name: str | None = None
    created_at: datetime | None = None
