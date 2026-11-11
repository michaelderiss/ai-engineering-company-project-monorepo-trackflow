"""Dedicated PostgreSQL connection for telemetry storage and reporting.

Inventory continues to use ``DATABASE_URL``. Telemetry uses
``TELEMETRY_DATABASE_URL`` so configuring Supabase for telemetry does not move
or initialize the inventory database there.
"""

from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


@lru_cache(maxsize=1)
def _engine_for_url(database_url: str) -> Engine:
    """Create a pooled PostgreSQL engine, requiring encrypted connections."""
    url = make_url(database_url)
    if url.drivername == "postgres":
        url = url.set(drivername="postgresql")
    if url.drivername not in {"postgresql", "postgresql+psycopg2"}:
        raise RuntimeError("TELEMETRY_DATABASE_URL must use PostgreSQL.")

    query = dict(url.query)
    # Supabase requires SSL. Require it when the URI omitted the parameter or
    # selected a non-verifying mode, while preserving stronger verification.
    if query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        query["sslmode"] = "require"
    url = url.set(query=query)
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def get_telemetry_engine() -> Engine:
    """Return the telemetry engine or fail clearly when it is not configured."""
    database_url = os.getenv("TELEMETRY_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("TELEMETRY_DATABASE_URL is not configured.")
    return _engine_for_url(database_url)