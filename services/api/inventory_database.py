from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import Engine, event, func, select
from sqlmodel import Session, SQLModel, create_engine

from services.api.inventory_models import SKU, StockEntry, StockExit

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    database_engine = create_engine(
        database_url,
        connect_args=connect_args,
        pool_pre_ping=not database_url.startswith("sqlite"),
    )
    if database_url.startswith("sqlite"):
        @event.listens_for(database_engine, "connect")
        def enable_sqlite_foreign_keys(connection, _record) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return database_engine


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set for inventory storage.")

engine = create_database_engine(DATABASE_URL)

SKU_SEED = [
    {
        "name": "Classic White Sneaker - Size 42",
        "sku": "CLT-SNK-W-42",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "Classic White Sneaker - Size 42",
        "sku": "CLT-SNK-W-42-Z",
        "client_name": "PureStep Footwear",
        "category": "fashion",
        "warehouse": "ZGZ",
    },
    {
        "name": "Wireless Earbuds Pro",
        "sku": "TEC-EAR-001",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "LA",
    },
    {
        "name": "Hydrating Face Serum 30ml",
        "sku": "CSM-SRM-030",
        "client_name": "GlowLab Cosmetics",
        "category": "cosmetics",
        "warehouse": "ZGZ",
    },
    {
        "name": "Slim Fit Chino - Navy 32/32",
        "sku": "CLT-CHN-N-32",
        "client_name": "UrbanThread",
        "category": "fashion",
        "warehouse": "LA",
    },
    {
        "name": "USB-C Fast Charger 65W",
        "sku": "TEC-CHG-065",
        "client_name": "SoundWave Electronics",
        "category": "electronics",
        "warehouse": "ZGZ",
    },
]

ENTRY_SEED = [
    {"sku": "CLT-SNK-W-42", "quantity": 20, "reference": "PO-2024-0098", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 8, "reference": "GR-LA-0234", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 16, "reference": "PO-2024-0112", "warehouse": "ZGZ"},
    {"sku": "TEC-EAR-001", "quantity": 12, "reference": "GR-LA-0291", "warehouse": "LA"},
]

EXIT_SEED = [
    {
        "sku": "CLT-SNK-W-42",
        "quantity": 3,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10123456784",
        "warehouse": "LA",
    },
    {
        "sku": "CLT-SNK-W-42-Z",
        "quantity": 2,
        "exit_type": "loss",
        "tracking_number": None,
        "warehouse": "ZGZ",
    },
    {
        "sku": "TEC-EAR-001",
        "quantity": 1,
        "exit_type": "dispatch",
        "tracking_number": "1Z999AA10987654321",
        "warehouse": "LA",
    },
]


def get_inventory_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _seed_user_uuid() -> str:
    from services.api.database import get_user_by_email

    admin_email = os.getenv("TRACKFLOW_ADMIN_EMAIL", "admin@trackflow.com")
    admin = get_user_by_email(admin_email)
    if admin is None:
        raise RuntimeError("The TinyDB admin user is required before inventory seeding.")
    return str(admin.id)


def seed_inventory_data() -> dict[str, int]:
    user_uuid = _seed_user_uuid()
    inserted = {"skus": 0, "stock_entries": 0, "stock_exits": 0}

    with Session(engine) as session:
        sku_by_code = {
            item.sku: item for item in session.scalars(select(SKU)).all()
        }
        for values in SKU_SEED:
            if values["sku"] not in sku_by_code:
                item = SKU(**values)
                session.add(item)
                sku_by_code[item.sku] = item
                inserted["skus"] += 1
        session.flush()

        for values in ENTRY_SEED:
            sku = sku_by_code[values["sku"]]
            existing = session.exec(
                select(StockEntry).where(
                    StockEntry.sku_id == sku.id,
                    StockEntry.quantity == values["quantity"],
                    StockEntry.reference == values["reference"],
                    StockEntry.warehouse == values["warehouse"],
                    StockEntry.user_uuid == user_uuid,
                )
            ).first()
            if existing is None:
                session.add(
                    StockEntry(
                        sku_id=sku.id,
                        quantity=values["quantity"],
                        reference=values["reference"],
                        warehouse=values["warehouse"],
                        user_uuid=user_uuid,
                    )
                )
                inserted["stock_entries"] += 1

        for values in EXIT_SEED:
            sku = sku_by_code[values["sku"]]
            existing = session.exec(
                select(StockExit).where(
                    StockExit.sku_id == sku.id,
                    StockExit.quantity == values["quantity"],
                    StockExit.exit_type == values["exit_type"],
                    StockExit.tracking_number == values["tracking_number"],
                    StockExit.warehouse == values["warehouse"],
                    StockExit.user_uuid == user_uuid,
                )
            ).first()
            if existing is None:
                session.add(
                    StockExit(
                        sku_id=sku.id,
                        quantity=values["quantity"],
                        exit_type=values["exit_type"],
                        tracking_number=values["tracking_number"],
                        warehouse=values["warehouse"],
                        user_uuid=user_uuid,
                    )
                )
                inserted["stock_exits"] += 1

        session.commit()

    return inserted


def initialize_inventory_database() -> dict[str, int]:
    SQLModel.metadata.create_all(engine)
    return seed_inventory_data()


def stock_totals(session: Session, sku_id: int, warehouse: str) -> tuple[int, int]:
    entries = session.scalar(
        select(func.coalesce(func.sum(StockEntry.quantity), 0)).where(
            StockEntry.sku_id == sku_id,
            StockEntry.warehouse == warehouse,
        )
    )
    exits = session.scalar(
        select(func.coalesce(func.sum(StockExit.quantity), 0)).where(
            StockExit.sku_id == sku_id,
            StockExit.warehouse == warehouse,
        )
    )
    return int(entries or 0), int(exits or 0)


def list_skus_with_stock(session: Session) -> list[dict[str, object]]:
    skus = session.scalars(select(SKU).order_by(SKU.id)).all()
    entry_rows = session.exec(
        select(StockEntry.sku_id, StockEntry.warehouse, func.sum(StockEntry.quantity)).group_by(
            StockEntry.sku_id, StockEntry.warehouse
        )
    ).all()
    exit_rows = session.exec(
        select(StockExit.sku_id, StockExit.warehouse, func.sum(StockExit.quantity)).group_by(
            StockExit.sku_id, StockExit.warehouse
        )
    ).all()
    entries = {(sku_id, warehouse): int(quantity) for sku_id, warehouse, quantity in entry_rows}
    exits = {(sku_id, warehouse): int(quantity) for sku_id, warehouse, quantity in exit_rows}

    return [
        {
            "id": sku.id,
            "name": sku.name,
            "sku": sku.sku,
            "client_name": sku.client_name,
            "category": sku.category,
            "warehouse": sku.warehouse,
            "current_stock": entries.get((sku.id, sku.warehouse), 0)
            - exits.get((sku.id, sku.warehouse), 0),
        }
        for sku in skus
    ]