from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from services.api.auth import get_current_user
from services.api.inventory_database import (
    get_inventory_session,
    list_skus_with_stock,
    stock_totals,
)
from services.api.inventory_models import SKU, StockEntry, StockExit
from services.api.inventory_schemas import (
    SKUCreate,
    SKURead,
    SKUReference,
    StockEntryCreate,
    StockEntryRead,
    StockExitCreate,
    StockExitRead,
    StockOrderRead,
)
from services.api.models import User

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _sku_response(sku: SKU, session: Session) -> SKURead:
    entries, exits = stock_totals(session, sku.id, sku.warehouse)
    return SKURead(
        id=sku.id,
        name=sku.name,
        sku=sku.sku,
        client_name=sku.client_name,
        category=sku.category,
        warehouse=sku.warehouse,
        current_stock=entries - exits,
    )


def _ensure_sku_warehouse(sku: SKU, warehouse: str) -> None:
    if sku.warehouse != warehouse:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU '{sku.sku}' is assigned to warehouse {sku.warehouse}.",
        )


@router.get("/products", response_model=list[SKURead])
def get_products(session: Session = Depends(get_inventory_session)) -> list[SKURead]:
    return [SKURead(**row) for row in list_skus_with_stock(session)]


@router.post(
    "/products",
    response_model=SKURead,
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
        raise HTTPException(status_code=409, detail="A SKU with this code already exists.") from exc
    session.refresh(sku)
    return _sku_response(sku, session)


@router.get("/products/{sku_id}", response_model=SKURead)
def get_product(
    sku_id: int,
    session: Session = Depends(get_inventory_session),
) -> SKURead:
    sku = session.get(SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    return _sku_response(sku, session)


@router.post(
    "/orders/inbound",
    response_model=StockEntryRead,
    status_code=status.HTTP_201_CREATED,
)
def post_inbound_order(
    payload: StockEntryCreate,
    session: Session = Depends(get_inventory_session),
    current_user: User = Depends(get_current_user),
) -> StockEntry:
    sku = session.get(SKU, payload.sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found.")
    _ensure_sku_warehouse(sku, payload.warehouse)

    entry = StockEntry(**payload.dict(), user_uuid=str(current_user.id))
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


@router.post(
    "/orders/outbound",
    response_model=StockExitRead,
    status_code=status.HTTP_201_CREATED,
)
def post_outbound_order(
    payload: StockExitCreate,
    session: Session = Depends(get_inventory_session),
    current_user: User = Depends(get_current_user),
) -> StockExit:
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
    session.refresh(stock_exit)
    return stock_exit


@router.get("/orders", response_model=list[StockOrderRead])
def get_orders(
    session: Session = Depends(get_inventory_session),
) -> list[StockOrderRead]:
    inbound_rows = session.exec(
        select(StockEntry, SKU).join(SKU, StockEntry.sku_id == SKU.id)
    ).all()
    outbound_rows = session.exec(
        select(StockExit, SKU).join(SKU, StockExit.sku_id == SKU.id)
    ).all()
    orders: list[StockOrderRead] = []

    for entry, sku in inbound_rows:
        orders.append(
            StockOrderRead(
                id=entry.id,
                order_type="inbound",
                sku_id=entry.sku_id,
                quantity=entry.quantity,
                reference=entry.reference,
                warehouse=entry.warehouse,
                created_at=entry.created_at,
                user_uuid=entry.user_uuid,
                sku=SKUReference.from_orm(sku),
            )
        )
    for stock_exit, sku in outbound_rows:
        orders.append(
            StockOrderRead(
                id=stock_exit.id,
                order_type="outbound",
                sku_id=stock_exit.sku_id,
                quantity=stock_exit.quantity,
                exit_type=stock_exit.exit_type,
                tracking_number=stock_exit.tracking_number,
                warehouse=stock_exit.warehouse,
                created_at=stock_exit.created_at,
                user_uuid=stock_exit.user_uuid,
                sku=SKUReference.from_orm(sku),
            )
        )

    return sorted(orders, key=lambda order: (order.created_at, order.order_type, order.id), reverse=True)