from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from packages.shared.incidents import (
    BRANCHES, CATEGORIES, ORIGINS, STATUSES, TRANSITIONS,
    Incident, IncidentBranch, IncidentCategory, IncidentCreate, IncidentOrigin,
    IncidentStatus, IncidentStatusUpdate,
)
from services.api import incidents as store
from services.api.auth import get_current_user
from services.api.cache import cached_json, summary_cache
from services.api.models import User
from services.api.response_schemas import (
    IncidentOptionsResponse,
    IncidentResponse,
    IncidentSummaryResponse,
)

router = APIRouter(prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])


@router.get("/options", response_model=IncidentOptionsResponse)
def options():
    return {"branches": BRANCHES, "categories": CATEGORIES, "statuses": STATUSES, "origins": ORIGINS, "transitions": TRANSITIONS}


@router.get("/summary", response_model=IncidentSummaryResponse)
def summary(current_user: User = Depends(get_current_user)):
    return cached_json(summary_cache, (store.DB_PATH, current_user.id), store.summary)


@router.post("", response_model=IncidentResponse, status_code=201)
def create_incident(payload: IncidentCreate):
    return store.create_incident(payload)


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: IncidentBranch | None = None,
    category: IncidentCategory | None = None,
):
    return store.list_incidents(status=status, origin=origin, branch=branch, category=category)


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int):
    record = store.get_incident(incident_id)
    if record is None:
        raise HTTPException(404, "Incident not found.")
    return record


@router.patch("/{incident_id}/status", response_model=IncidentResponse)
def update_status(incident_id: int, payload: IncidentStatusUpdate):
    try:
        record = store.update_status(incident_id, payload.status)
    except ValueError as exc:
        raise HTTPException(400, {"status": str(exc)}) from exc
    if record is None:
        raise HTTPException(404, "Incident not found.")
    return record