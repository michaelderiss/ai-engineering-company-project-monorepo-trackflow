"""Typed read-only tools used by the TrackFlow support agent."""

from __future__ import annotations

import concurrent.futures
from typing import Literal

from pydantic import BaseModel, Field

from services.api import incidents as incident_store


INCIDENT_LOOKUP_TIMEOUT_SECONDS = 3.0


class TicketLookupInput(BaseModel):
    ticket_id: int = Field(..., gt=0)


class TicketLookupOutput(BaseModel):
    found: bool
    ticket_id: int
    status: str | None = None
    category: str | None = None
    origin: str | None = None
    branch: str | None = None
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    fallback: Literal["none", "not_found", "timeout", "error"] = "none"


def lookup_ticket(ticket_id: int) -> TicketLookupOutput:
    """Read one incident from the real incident manager with a numeric timeout."""

    lookup = TicketLookupInput(ticket_id=ticket_id)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(incident_store.get_incident, lookup.ticket_id)
    try:
        record = future.result(timeout=INCIDENT_LOOKUP_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        return TicketLookupOutput(
            found=False,
            ticket_id=lookup.ticket_id,
            fallback="timeout",
        )
    except Exception:
        executor.shutdown(wait=False, cancel_futures=True)
        return TicketLookupOutput(
            found=False,
            ticket_id=lookup.ticket_id,
            fallback="error",
        )
    finally:
        if future.done():
            executor.shutdown(wait=False, cancel_futures=True)

    if record is None:
        return TicketLookupOutput(
            found=False,
            ticket_id=lookup.ticket_id,
            fallback="not_found",
        )

    return TicketLookupOutput(
        found=True,
        ticket_id=lookup.ticket_id,
        status=str(record.get("status")) if record.get("status") is not None else None,
        category=str(record.get("category")) if record.get("category") is not None else None,
        origin=str(record.get("origin")) if record.get("origin") is not None else None,
        branch=str(record.get("branch")) if record.get("branch") is not None else None,
        title=str(record.get("title")) if record.get("title") is not None else None,
        created_at=str(record.get("created_at")) if record.get("created_at") is not None else None,
        updated_at=str(record.get("updated_at")) if record.get("updated_at") is not None else None,
    )
