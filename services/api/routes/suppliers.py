from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.auth import get_current_user
from services.api.database import (
    create_supplier,
    delete_supplier,
    get_supplier_by_id,
    list_suppliers,
    update_supplier_rate,
    update_supplier_status,
)
from services.api.models import (
    VALID_CATEGORIES,
    Country,
    Supplier,
    SupplierCreate,
    SupplierRateUpdate,
    SupplierStatusUpdate,
    User,
)
from services.api.response_schemas import DeleteResponse, SupplierResponse

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def post_supplier(
    payload: SupplierCreate,
    current_user: User = Depends(get_current_user),
) -> SupplierResponse:
    return create_supplier(payload)


@router.get("", response_model=list[SupplierResponse])
def get_suppliers(
    country: Country | None = None,
    category: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
) -> list[SupplierResponse]:
    if category is not None and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=422, detail="Invalid category filter.")
    return list_suppliers(country.value if country else None, category)


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier(supplier_id: int, current_user: User = Depends(get_current_user)) -> SupplierResponse:
    supplier = get_supplier_by_id(supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


@router.patch("/{supplier_id}/rate", response_model=SupplierResponse)
def patch_supplier_rate(
    supplier_id: int,
    payload: SupplierRateUpdate,
    current_user: User = Depends(get_current_user),
) -> SupplierResponse:
    supplier = update_supplier_rate(supplier_id, payload.rate_per_shipment)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


@router.patch("/{supplier_id}/status", response_model=SupplierResponse)
def patch_supplier_status(
    supplier_id: int,
    payload: SupplierStatusUpdate,
    current_user: User = Depends(get_current_user),
) -> SupplierResponse:
    supplier = update_supplier_status(supplier_id, payload.status)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


@router.delete("/{supplier_id}", response_model=DeleteResponse)
def remove_supplier(
    supplier_id: int,
    current_user: User = Depends(get_current_user),
) -> DeleteResponse:
    deleted = delete_supplier(supplier_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return {"deleted": True, "id": supplier_id}
