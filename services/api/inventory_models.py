from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SKU(SQLModel, table=True):
    __tablename__ = "inventory_skus"
    __table_args__ = (
        CheckConstraint("category IN ('fashion', 'electronics', 'cosmetics')"),
        CheckConstraint("warehouse IN ('LA', 'ZGZ')"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1, max_length=255)
    sku: str = Field(min_length=1, max_length=80, unique=True, index=True)
    client_name: str = Field(min_length=1, max_length=160)
    category: str = Field(max_length=32)
    warehouse: str = Field(max_length=3, index=True)


class StockEntry(SQLModel, table=True):
    __tablename__ = "inventory_stock_entries"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("warehouse IN ('LA', 'ZGZ')"),
    )

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="inventory_skus.id", index=True)
    quantity: int = Field(gt=0)
    reference: str = Field(min_length=1, max_length=120)
    warehouse: str = Field(max_length=3, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    user_uuid: str = Field(min_length=1, max_length=100, index=True)


class StockExit(SQLModel, table=True):
    __tablename__ = "inventory_stock_exits"
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        CheckConstraint("warehouse IN ('LA', 'ZGZ')"),
        CheckConstraint("exit_type IN ('dispatch', 'loss')"),
        CheckConstraint(
            "(exit_type = 'dispatch' AND tracking_number IS NOT NULL "
            "AND length(trim(tracking_number)) > 0) OR "
            "(exit_type = 'loss' AND tracking_number IS NULL)"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="inventory_skus.id", index=True)
    quantity: int = Field(gt=0)
    exit_type: str = Field(max_length=16)
    tracking_number: str | None = Field(default=None, max_length=120)
    warehouse: str = Field(max_length=3, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    user_uuid: str = Field(min_length=1, max_length=100, index=True)