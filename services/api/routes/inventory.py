from __future__ import annotations

from collections import OrderedDict
from threading import RLock

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from services.api.auth import get_current_user
from services.api.cache import cached_json, catalog_cache
from services.api.inventory_database import (
    get_inventory_session,
    list_skus_with_stock,
    stock_totals,
)
from services.api.inventory_models import SKU, StockEntry, StockExit
from services.api.inventory_schemas import (
    DiscrepancyReport,
    SKUCreate,
    StockEntryCreate,
    StockExitCreate,
)
from services.api.models import User
from services.api.response_schemas import (
    SKUReferenceResponse,
    SKUResponse,
    StockEntryResponse,
    StockExitResponse,
    StockOrderResponse,
)
from services.api import telemetry as telemetry_module

router = APIRouter(prefix="/inventory", tags=["inventory"])

# Crossing tracker for stock_threshold_triggered — thread-safe, capped.
# Keyed by (sku_id, warehouse), tracks whether the SKU is currently below min.
_threshold_below: dict[tuple[int, str], bool] = {}
_threshold_lock = RLock()
_CLIENT_IDS = {
    "PureStep Footwear": "purestep_footwear",
    "SoundWave Electronics": "soundwave_electronics",
    "GlowLab Cosmetics": "glowlab_cosmetics",
    "UrbanThread": "urbanthread",
}


def _emit_stock_threshold(sku: SKU, current_stock: int) -> None:
    """Emit stock_threshold_triggered if a crossing occurs.

    Crossing = SKU was at/above minimum and is now below minimum.
    Re-arms only when stock returns to or above minimum.
    """
    min_stock = sku.minimum_stock or 0
    client_id = _CLIENT_IDS.get(sku.client_name)
    if not client_id:
        return
    key = (sku.id, sku.warehouse)
    with _threshold_lock:
        previously_below = _threshold_below.get(key, False)
        now_below = current_stock < min_stock

        if now_below and not previously_below:
            _threshold_below[key] = True
            telemetry_module.record_server_event(
                "stock_threshold_triggered",
                {
                    "warehouse": "los_angeles" if sku.warehouse == "LA" else "zaragoza",
                    "client_id": client_id,
                    "product_id": sku.sku,
                    "product_category": sku.category,
                    "quantity": current_stock,
                    "minimum_stock": min_stock,
                },
            )
        elif not now_below and previously_below:
            # Re-arm: stock is now at or above minimum again
            _threshold_below[key] = False


def _sku_response(sku: SKU, session: Session) -> SKUResponse:
    entries, exits = stock_totals(session, sku.id, sku.warehouse)
    return SKUResponse(
        id=sku.id,
        name=sku.name,
        sku=sku.sku,
        client_name=sku.client_name,
        category=sku.category,
        warehouse=sku.warehouse,
        current_stock=entries - exits,
        minimum_stock=sku.minimum_stock,
    )


def _ensure_sku_warehouse(sku: SKU, warehouse: str) -> None:
    if sku.warehouse != warehouse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU '{sku.sku}' is assigned to warehouse {sku.warehouse}.",
        )


@router.get("/products", response_model=list[SKUResponse])
def get_products(session: Session = Depends(get_inventory_session)):
    return cached_json(
        catalog_cache,
        session.get_bind(),
        lambda: [SKUResponse(**row) for row in list_skus_with_stock(session)],
    )


@router.post(
    "/products",
    response_model=SKUResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_product(
    payload: SKUCreate,
    session: Session = Depends(get_inventory_session),
    current_user: User = Depends(get_current_user),
) -> SKURead:
    del current_user
    sku = SKU(**payload.dict())
    session.add(sku)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="A SKU with this code already exists."
        ) from exc
    catalog_cache.clear()
    session.refresh(sku)
    return _sku_response(sku, session)


@router.get("/products/{sku_id}", response_model=SKUResponse)
def get_product(
    sku_id: int,
    session: Session = Depends(get_inventory_session),
) -> SKUResponse:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    return _sku_response(sku, session)


@router.post(
    "/orders/inbound",
    response_model=StockEntryResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_inbound_order(
    payload: StockEntryCreate,
    session: Session = Depends(get_inventory_session),
    current_user: User = Depends(get_current_user),
) -> StockEntryResponse:
    sku = session.get(SKU, payload.sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    _ensure_sku_warehouse(sku, payload.warehouse)

    entry = StockEntry(**payload.dict(), user_uuid=str(current_user.id))
    session.add(entry)
    session.commit()
    catalog_cache.clear()
    session.refresh(entry)
    return entry


@router.post(
    "/orders/outbound",
    response_model=StockExitResponse,
    status_code=status.HTTP_201_CREATED,
)
def post_outbound_order(
    payload: StockExitCreate,
    session: Session = Depends(get_inventory_session),
    current_user: User = Depends(get_current_user),
) -> StockExitResponse:
    sku = session.exec(
        select(SKU)
        .where(SKU.id == payload.sku_id, SKU.warehouse == payload.warehouse)
        .with_for_update()
    ).first()
    if sku is None:
        existing_sku = session.get(SKU, payload.sku_id)
        if existing_sku is None:
            raise HTTPException(status_code=404, detail="SKU not found.")
        _ensure_sku_warehouse(existing_sku, payload.warehouse)

    entries, exits = stock_totals(session, sku.id, payload.warehouse)
    available = entries - exits
    if payload.quantity > available:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock for SKU '{sku.sku}'. Available: {available}, "
                f"requested: {payload.quantity}."
            ),
        )

    stock_exit = StockExit(**payload.dict(), user_uuid=str(current_user.id))
    session.add(stock_exit)
    session.commit()
    catalog_cache.clear()
    session.refresh(stock_exit)

    new_available = (entries - exits) - payload.quantity
    _emit_stock_threshold(sku, new_available)

    return stock_exit


@router.get("/orders", response_model=list[StockOrderResponse])
def get_orders(
    session: Session = Depends(get_inventory_session),
) -> list[StockOrderResponse]:
    inbound_rows = session.exec(
        select(StockEntry, SKU).join(SKU, StockEntry.sku_id == SKU.id)
    ).all()
    outbound_rows = session.exec(
        select(StockExit, SKU).join(SKU, StockExit.sku_id == SKU.id)
    ).all()
    orders: list[StockOrderResponse] = []

    for entry, sku in inbound_rows:
        orders.append(
            StockOrderResponse(
                id=entry.id,
                order_type="inbound",
                sku_id=entry.sku_id,
                quantity=entry.quantity,
                reference=entry.reference,
                warehouse=entry.warehouse,
                created_at=entry.created_at,
                sku=SKUReferenceResponse.from_orm(sku),
            )
        )
    for stock_exit, sku in outbound_rows:
        orders.append(
            StockOrderResponse(
                id=stock_exit.id,
                order_type="outbound",
                sku_id=stock_exit.sku_id,
                quantity=stock_exit.quantity,
                exit_type=stock_exit.exit_type,
                tracking_number=stock_exit.tracking_number,
                warehouse=stock_exit.warehouse,
                created_at=stock_exit.created_at,
                sku=SKUReferenceResponse.from_orm(sku),
            )
        )

    return sorted(
        orders,
        key=lambda order: (order.created_at, order.order_type, order.id),
        reverse=True,
    )


@router.post("/discrepancy", status_code=status.HTTP_201_CREATED)
def report_discrepancy(
    payload: DiscrepancyReport,
    session: Session = Depends(get_inventory_session),
) -> dict[str, object]:
    """Record a physical-count discrepancy and emit an inventory_discrepancy_detected event."""
    sku = session.get(SKU, payload.sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    if sku.warehouse != payload.warehouse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU '{sku.sku}' is assigned to warehouse {sku.warehouse}.",
        )

    discrepancy = abs(payload.physical_quantity - payload.system_quantity)
    client_id = _CLIENT_IDS.get(sku.client_name)
    if client_id and discrepancy > 0:
        telemetry_module.record_server_event("inventory_discrepancy_detected", {
            "warehouse": "los_angeles" if payload.warehouse == "LA" else "zaragoza",
            "client_id": client_id,
            "product_id": sku.sku,
            "product_category": sku.category,
            "quantity": discrepancy,
            "system_quantity": payload.system_quantity,
            "physical_quantity": payload.physical_quantity,
        })

    return {
        "sku_id": payload.sku_id,
        "warehouse": payload.warehouse,
        "system_quantity": payload.system_quantity,
        "physical_quantity": payload.physical_quantity,
        "discrepancy": discrepancy,
    }