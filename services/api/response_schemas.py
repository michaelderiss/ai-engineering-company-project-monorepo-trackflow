from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from services.api.models import Country, Currency, Role, SupplierStatus


class MessageResponse(BaseModel):
    message: str


class DeleteResponse(BaseModel):
    deleted: bool
    id: int


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ProfileResponse(BaseModel):
    id: int
    user_id: int
    display_name: str
    phone: str | None = None
    address: str | None = None

    class Config:
        orm_mode = True


class CurrentUserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    role: Role
    created_at: datetime
    updated_at: datetime
    profile: ProfileResponse | None = None


class UserResponse(BaseModel):
    id: int
    is_active: bool
    role: Role
    created_at: datetime
    updated_at: datetime


class UserCreatedResponse(BaseModel):
    id: int
    is_active: bool
    role: Role
    created_at: datetime
    updated_at: datetime


class SupplierResponse(BaseModel):
    id: int
    name: str
    country: Country
    categories: list[str]
    rate_per_shipment: float
    currency: Currency
    status: SupplierStatus
    service_zone: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    updated_at: datetime


class IncidentResponse(BaseModel):
    id: int
    title: str
    description: str
    category: str
    status: str
    origin: str
    branch: str
    created_at: datetime
    updated_at: datetime


class IncidentOptionsResponse(BaseModel):
    branches: dict[str, str]
    categories: dict[str, str]
    statuses: dict[str, str]
    origins: dict[str, str]
    transitions: dict[str, list[str]]


class IncidentSummaryResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    by_origin: dict[str, int]
    by_branch: dict[str, int]


class IncidentAnalysisResponse(BaseModel):
    total_records: int
    valid_records: int
    invalid_records: int
    invalid_breakdown: dict[str, int]
    category_breakdown: dict[str, int]
    status_breakdown: dict[str, int]
    country_breakdown: dict[str, int]
    satisfaction_breakdown: dict[int, int]
    satisfaction_average: float
    scored_closed_incidents: int
    closed_incidents: int
    source_file: str


class SKUResponse(BaseModel):
    id: int
    name: str
    sku: str
    client_name: str
    category: Literal["fashion", "electronics", "cosmetics"]
    warehouse: Literal["LA", "ZGZ"]
    current_stock: int


class StockEntryResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    reference: str
    warehouse: Literal["LA", "ZGZ"]
    created_at: datetime


class StockExitResponse(BaseModel):
    id: int
    sku_id: int
    quantity: int
    exit_type: Literal["dispatch", "loss"]
    tracking_number: str | None = None
    warehouse: Literal["LA", "ZGZ"]
    created_at: datetime


class SKUReferenceResponse(BaseModel):
    id: int
    name: str
    sku: str
    client_name: str
    category: Literal["fashion", "electronics", "cosmetics"]
    warehouse: Literal["LA", "ZGZ"]

    class Config:
        orm_mode = True


class StockOrderResponse(BaseModel):
    id: int
    order_type: Literal["inbound", "outbound"]
    sku_id: int
    quantity: int
    reference: str | None = None
    exit_type: Literal["dispatch", "loss"] | None = None
    tracking_number: str | None = None
    warehouse: Literal["LA", "ZGZ"]
    created_at: datetime
    sku: SKUReferenceResponse
