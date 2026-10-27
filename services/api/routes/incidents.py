from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from packages.shared.incidents import (
    BRANCHES, CATEGORIES, ORIGINS, STATUSES, TRANSITIONS,
    Incident, IncidentBranch, IncidentCategory, IncidentCreate, IncidentOrigin,
    IncidentStatus, IncidentStatusUpdate,
)
from services.api import incidents as store
from services.api.auth import get_current_user

router = APIRouter(prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])


@router.get("/options")
def options():
    return {"branches": BRANCHES, "categories": CATEGORIES, "statuses": STATUSES, "origins": ORIGINS, "transitions": TRANSITIONS}


@router.get("/summary")
def summary():
    return store.summary()


@router.post("", response_model=Incident, status_code=201)
def create_incident(payload: IncidentCreate):
    return store.create_incident(payload)


@router.get("", response_model=list[Incident])
def list_incidents(
    status: IncidentStatus | None = None,
    origin: IncidentOrigin | None = None,
    branch: IncidentBranch | None = None,
    category: IncidentCategory | None = None,
):
    return store.list_incidents(status=status, origin=origin, branch=branch, category=category)


@router.get("/{incident_id}", response_model=Incident)
def get_incident(incident_id: int):
    record = store.get_incident(incident_id)
    if record is None:
        raise HTTPException(404, "Incident not found.")
    return record


@router.patch("/{incident_id}/status", response_model=Incident)
def update_status(incident_id: int, payload: IncidentStatusUpdate):
    try:
        record = store.update_status(incident_id, payload.status)
    except ValueError as exc:
        raise HTTPException(400, {"status": str(exc)}) from exc
    if record is None:
        raise HTTPException(404, "Incident not found.")
    return record