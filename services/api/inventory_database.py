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
    # PureStep Footwear — fashion — Los Angeles (2) + Zaragoza (2)
    {"name": "Classic White Sneaker - Size 42", "sku": "CLT-SNK-W-42", "client_name": "PureStep Footwear", "category": "fashion", "warehouse": "LA", "minimum_stock": 10},
    {"name": "Classic White Sneaker - Size 42", "sku": "CLT-SNK-W-42-Z", "client_name": "PureStep Footwear", "category": "fashion", "warehouse": "ZGZ", "minimum_stock": 8},
    {"name": "Black Leather Boot - Size 44", "sku": "CLT-BOT-B-44", "client_name": "PureStep Footwear", "category": "fashion", "warehouse": "LA", "minimum_stock": 5},
    {"name": "Organic Cotton T-Shirt - White M", "sku": "CLT-TSH-W-M", "client_name": "PureStep Footwear", "category": "fashion", "warehouse": "ZGZ", "minimum_stock": 15},
    # SoundWave Electronics — electronics — both warehouses
    {"name": "Wireless Earbuds Pro", "sku": "TEC-EAR-001", "client_name": "SoundWave Electronics", "category": "electronics", "warehouse": "LA", "minimum_stock": 6},
    {"name": "USB-C Fast Charger 65W", "sku": "TEC-CHG-065", "client_name": "SoundWave Electronics", "category": "electronics", "warehouse": "ZGZ", "minimum_stock": 4},
    {"name": "Bluetooth Speaker Waterproof", "sku": "TEC-SPK-001", "client_name": "SoundWave Electronics", "category": "electronics", "warehouse": "LA", "minimum_stock": 3},
    {"name": "Smartphone Tripod Stand", "sku": "TEC-TRP-001", "client_name": "SoundWave Electronics", "category": "electronics", "warehouse": "ZGZ", "minimum_stock": 2},
    # GlowLab Cosmetics — cosmetics — Los Angeles
    {"name": "Hydrating Face Serum 30ml", "sku": "CSM-SRM-030", "client_name": "GlowLab Cosmetics", "category": "cosmetics", "warehouse": "ZGZ", "minimum_stock": 10},
    {"name": "Vitamin C Night Cream 50ml", "sku": "CSM-CRM-050", "client_name": "GlowLab Cosmetics", "category": "cosmetics", "warehouse": "LA", "minimum_stock": 8},
]

ENTRY_SEED = [
    # PureStep LA — CLT-SNK-W-42 (minimum 10)
    {"sku": "CLT-SNK-W-42", "quantity": 20, "reference": "PO-2024-0098", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 8, "reference": "GR-LA-0234", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 5, "reference": "PO-2024-0105", "warehouse": "LA"},
    # PureStep ZGZ — CLT-SNK-W-42-Z (minimum 8)
    {"sku": "CLT-SNK-W-42-Z", "quantity": 16, "reference": "PO-2024-0112", "warehouse": "ZGZ"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 4, "reference": "GR-ZGZ-0118", "warehouse": "ZGZ"},
    # PureStep LA — CLT-BOT-B-44 (minimum 5)
    {"sku": "CLT-BOT-B-44", "quantity": 10, "reference": "PO-2024-0123", "warehouse": "LA"},
    # PureStep ZGZ — CLT-TSH-W-M (minimum 15)
    {"sku": "CLT-TSH-W-M", "quantity": 20, "reference": "PO-2024-0130", "warehouse": "ZGZ"},
    {"sku": "CLT-TSH-W-M", "quantity": 15, "reference": "GR-ZGZ-0134", "warehouse": "ZGZ"},
    # SoundWave LA — TEC-EAR-001 (minimum 6)
    {"sku": "TEC-EAR-001", "quantity": 12, "reference": "GR-LA-0291", "warehouse": "LA"},
    {"sku": "TEC-EAR-001", "quantity": 8, "reference": "PO-2024-0295", "warehouse": "LA"},
    # SoundWave ZGZ — TEC-CHG-065 (minimum 4)
    {"sku": "TEC-CHG-065", "quantity": 10, "reference": "PO-2024-0302", "warehouse": "ZGZ"},
    # SoundWave LA — TEC-SPK-001 (minimum 3)
    {"sku": "TEC-SPK-001", "quantity": 6, "reference": "PO-2024-0310", "warehouse": "LA"},
    # SoundWave ZGZ — TEC-TRP-001 (minimum 2)
    {"sku": "TEC-TRP-001", "quantity": 8, "reference": "PO-2024-0315", "warehouse": "ZGZ"},
    # GlowLab ZGZ — CSM-SRM-030 (minimum 10)
    {"sku": "CSM-SRM-030", "quantity": 14, "reference": "PO-2024-0322", "warehouse": "ZGZ"},
    {"sku": "CSM-SRM-030", "quantity": 6, "reference": "GR-ZGZ-0325", "warehouse": "ZGZ"},
    # GlowLab LA — CSM-CRM-050 (minimum 8)
    {"sku": "CSM-CRM-050", "quantity": 12, "reference": "PO-2024-0330", "warehouse": "LA"},
    {"sku": "CSM-CRM-050", "quantity": 8, "reference": "PO-2024-0334", "warehouse": "LA"},
    {"sku": "CSM-CRM-050", "quantity": 3, "reference": "GR-LA-0337", "warehouse": "LA"},
]

EXIT_SEED = [
    # CLT-SNK-W-42 LA — many dispatches will drive it below minimum 10 → triggers threshold
    {"sku": "CLT-SNK-W-42", "quantity": 3, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456784", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 5, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456785", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 4, "exit_type": "dispatch", "tracking_number": "1Z999AA10123456786", "warehouse": "LA"},
    {"sku": "CLT-SNK-W-42", "quantity": 6, "exit_type": "dispatch", "tracking_number": "1Z999AA20123456701", "warehouse": "LA"},
    # CLT-SNK-W-42-Z ZGZ — (minimum 8)
    {"sku": "CLT-SNK-W-42-Z", "quantity": 2, "exit_type": "loss", "tracking_number": None, "warehouse": "ZGZ"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 7, "exit_type": "dispatch", "tracking_number": "1Z999AA20123456702", "warehouse": "ZGZ"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 3, "exit_type": "dispatch", "tracking_number": "1Z999AA20123456703", "warehouse": "ZGZ"},
    {"sku": "CLT-SNK-W-42-Z", "quantity": 5, "exit_type": "dispatch", "tracking_number": "1Z999AA20123456704", "warehouse": "ZGZ"},
    # CLT-BOT-B-44 LA — (minimum 5) — stays above
    {"sku": "CLT-BOT-B-44", "quantity": 2, "exit_type": "dispatch", "tracking_number": "1Z999AA30123456701", "warehouse": "LA"},
    {"sku": "CLT-BOT-B-44", "quantity": 1, "exit_type": "dispatch", "tracking_number": "1Z999AA30123456702", "warehouse": "LA"},
    # CLT-TSH-W-M ZGZ — (minimum 15) — heavy dispatches trigger threshold
    {"sku": "CLT-TSH-W-M", "quantity": 10, "exit_type": "dispatch", "tracking_number": "1Z999AA40123456701", "warehouse": "ZGZ"},
    {"sku": "CLT-TSH-W-M", "quantity": 8, "exit_type": "dispatch", "tracking_number": "1Z999AA40123456702", "warehouse": "ZGZ"},
    {"sku": "CLT-TSH-W-M", "quantity": 5, "exit_type": "dispatch", "tracking_number": "1Z999AA40123456703", "warehouse": "ZGZ"},
    # TEC-EAR-001 LA — (minimum 6) — dispatches drive below threshold
    {"sku": "TEC-EAR-001", "quantity": 1, "exit_type": "dispatch", "tracking_number": "1Z999AA10987654321", "warehouse": "LA"},
    {"sku": "TEC-EAR-001", "quantity": 4, "exit_type": "dispatch", "tracking_number": "1Z999AA10987654322", "warehouse": "LA"},
    {"sku": "TEC-EAR-001", "quantity": 3, "exit_type": "dispatch", "tracking_number": "1Z999AA10987654323", "warehouse": "LA"},
    # TEC-CHG-065 ZGZ — (minimum 4) — stays above
    {"sku": "TEC-CHG-065", "quantity": 1, "exit_type": "dispatch", "tracking_number": "1Z999AA50123456701", "warehouse": "ZGZ"},
    {"sku": "TEC-CHG-065", "quantity": 2, "exit_type": "dispatch", "tracking_number": "1Z999AA50123456702", "warehouse": "ZGZ"},
    # TEC-SPK-001 LA — (minimum 3) — stays at threshold
    {"sku": "TEC-SPK-001", "quantity": 2, "exit_type": "dispatch", "tracking_number": "1Z999AA60123456701", "warehouse": "LA"},
    # TEC-TRP-001 ZGZ — (minimum 2) — stays above
    {"sku": "TEC-TRP-001", "quantity": 1, "exit_type": "loss", "tracking_number": None, "warehouse": "ZGZ"},
    # CSM-SRM-030 ZGZ — (minimum 10) — dispatches stay near threshold
    {"sku": "CSM-SRM-030", "quantity": 3, "exit_type": "dispatch", "tracking_number": "1Z999AA70123456701", "warehouse": "ZGZ"},
    {"sku": "CSM-SRM-030", "quantity": 5, "exit_type": "dispatch", "tracking_number": "1Z999AA70123456702", "warehouse": "ZGZ"},
    # CSM-CRM-050 LA — (minimum 8) — heavy dispatches + losses trigger threshold
    {"sku": "CSM-CRM-050", "quantity": 4, "exit_type": "dispatch", "tracking_number": "1Z999AA80123456701", "warehouse": "LA"},
    {"sku": "CSM-CRM-050", "quantity": 2, "exit_type": "loss", "tracking_number": None, "warehouse": "LA"},
    {"sku": "CSM-CRM-050", "quantity": 6, "exit_type": "dispatch", "tracking_number": "1Z999AA80123456702", "warehouse": "LA"},
    {"sku": "CSM-CRM-050", "quantity": 3, "exit_type": "dispatch", "tracking_number": "1Z999AA80123456703", "warehouse": "LA"},
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
            "minimum_stock": sku.minimum_stock,
        }
        for sku in skus
    ]