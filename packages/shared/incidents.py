from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, constr, validator

IncidentStatus = Literal["open", "in_progress", "resolved", "discarded"]
IncidentOrigin = Literal["customer", "branch", "internal"]
IncidentBranch = Literal["central", "la_warehouse", "la_office", "zaragoza_warehouse", "zaragoza_office"]
IncidentCategory = Literal[
    "lost_parcel", "delivery_failure", "inventory_discrepancy", "carrier_issue",
    "returns_issue", "warehouse_incident", "system_failure", "client_complaint", "other",
]

BRANCHES = {
    "central": "Central",
    "la_warehouse": "Los Angeles \u2014 Warehouse",
    "la_office": "Los Angeles \u2014 Office",
    "zaragoza_warehouse": "Zaragoza \u2014 Warehouse",
    "zaragoza_office": "Zaragoza \u2014 Office",
}
CATEGORIES = {
    "lost_parcel": "Lost parcel",
    "delivery_failure": "Delivery failure",
    "inventory_discrepancy": "Inventory discrepancy",
    "carrier_issue": "Carrier issue",
    "returns_issue": "Returns issue",
    "warehouse_incident": "Warehouse incident",
    "system_failure": "System failure",
    "client_complaint": "Client complaint",
    "other": "Other",
}
STATUSES = {"open": "Open", "in_progress": "In progress", "resolved": "Resolved", "discarded": "Discarded"}
ORIGINS = {"customer": "Customer", "branch": "Branch", "internal": "Internal"}
TRANSITIONS = {"open": ["in_progress", "discarded"], "in_progress": ["resolved", "discarded"], "resolved": [], "discarded": []}
CSV_STATUSES = {"OPEN": "open", "CLOSED": "resolved", "DISCARDED": "discarded"}
CSV_CATEGORIES = {
    "LOST_PARCEL": "lost_parcel", "DELAYED_DELIVERY": "carrier_issue",
    "WRONG_ADDRESS": "delivery_failure", "RETURN_REQUEST": "returns_issue", "DAMAGE": "carrier_issue",
}
CSV_BRANCHES = {"US": "la_office", "ES": "zaragoza_office"}


class IncidentCreate(BaseModel):
    title: constr(strip_whitespace=True, min_length=1, max_length=120)
    description: constr(min_length=1)
    category: IncidentCategory
    status: IncidentStatus
    origin: IncidentOrigin
    branch: IncidentBranch

    @validator("description")
    def description_required(cls, value):
        if not value.strip():
            raise ValueError("Please enter a description.")
        return value

    class Config:
        extra = "forbid"


class Incident(IncidentCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus

    class Config:
        extra = "forbid"