from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, root_validator

Warehouse = Literal["LA", "ZGZ"]
Category = Literal["fashion", "electronics", "cosmetics"]
ExitType = Literal["dispatch", "loss"]


class SKUCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=80)
    client_name: str = Field(..., min_length=1, max_length=160)
    category: Category
    warehouse: Warehouse

    class Config:
        extra = "forbid"


class SKURead(SKUCreate):
    id: int
    current_stock: int

    class Config:
        orm_mode = True


class StockEntryCreate(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    reference: str = Field(..., min_length=1, max_length=120)
    warehouse: Warehouse

    class Config:
        extra = "forbid"


class StockEntryRead(StockEntryCreate):
    id: int
    created_at: datetime
    user_uuid: str

    class Config:
        orm_mode = True


class StockExitCreate(BaseModel):
    sku_id: int = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    exit_type: ExitType
    tracking_number: str | None = Field(default=None, max_length=120)
    warehouse: Warehouse

    @root_validator
    def validate_tracking_number(cls, values: dict) -> dict:
        exit_type = values.get("exit_type")
        tracking_number = values.get("tracking_number")
        if exit_type == "dispatch" and (
            not tracking_number or not tracking_number.strip()
        ):
            raise ValueError("tracking_number is required for a dispatch.")
        if exit_type == "loss" and tracking_number is not None:
            raise ValueError("tracking_number must be null for a loss.")
        return values

    class Config:
        extra = "forbid"


class StockExitRead(StockExitCreate):
    id: int
    created_at: datetime
    user_uuid: str

    class Config:
        orm_mode = True


class SKUReference(BaseModel):
    id: int
    name: str
    sku: str
    client_name: str
    category: Category
    warehouse: Warehouse

    class Config:
        orm_mode = True


class StockOrderRead(BaseModel):
    id: int
    order_type: Literal["inbound", "outbound"]
    sku_id: int
    quantity: int
    reference: str | None = None
    exit_type: ExitType | None = None
    tracking_number: str | None = None
    warehouse: Warehouse
    created_at: datetime
    user_uuid: str
    sku: SKUReference