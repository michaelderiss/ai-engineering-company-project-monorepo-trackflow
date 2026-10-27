from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from packages.shared.incidents import BRANCHES, CATEGORIES, ORIGINS, STATUSES, TRANSITIONS, IncidentCreate

DB_PATH = Path(__file__).resolve().parent / "data" / "incidents.sqlite3"


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    constraints = {
        "category": CATEGORIES, "status": STATUSES, "origin": ORIGINS, "branch": BRANCHES,
    }
    checks = ", ".join(
        f"{field} TEXT NOT NULL CHECK ({field} IN ({','.join(repr(value) for value in values)}))"
        for field, values in constraints.items()
    )
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS incidents ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "title TEXT NOT NULL CHECK (length(trim(title)) BETWEEN 1 AND 120), "
            "description TEXT NOT NULL CHECK (length(trim(description)) > 0), "
            f"{checks}, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS incident_imports ("
            "source_key TEXT PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id))"
        )
        with db:
            yield db
    finally:
        db.close()


def create_incident(payload: IncidentCreate, created_at: str | None = None, source_key: str | None = None):
    now = created_at or datetime.now(timezone.utc).isoformat()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if source_key and db.execute("SELECT 1 FROM incident_imports WHERE source_key = ?", (source_key,)).fetchone():
            return None
        data = payload.dict()
        cursor = db.execute(
            "INSERT INTO incidents (title, description, category, status, origin, branch, created_at, updated_at) "
            "VALUES (:title, :description, :category, :status, :origin, :branch, :created_at, :updated_at)",
            {**data, "created_at": now, "updated_at": now},
        )
        if source_key:
            db.execute("INSERT INTO incident_imports VALUES (?, ?)", (source_key, cursor.lastrowid))
        return dict(db.execute("SELECT * FROM incidents WHERE id = ?", (cursor.lastrowid,)).fetchone())


def list_incidents(**filters):
    filters = {field: value for field, value in filters.items() if value is not None}
    clauses = [f"{field} = ?" for field in ("status", "origin", "branch", "category") if field in filters]
    values = [filters[field] for field in ("status", "origin", "branch", "category") if field in filters]
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connection() as db:
        return [dict(row) for row in db.execute("SELECT * FROM incidents" + where + " ORDER BY created_at DESC, id DESC", values)]


def get_incident(incident_id: int):
    with connection() as db:
        row = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        return dict(row) if row else None


def update_status(incident_id: int, status: str):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
        if row is None:
            return None
        if status not in TRANSITIONS[row["status"]]:
            raise ValueError("This status change is not allowed. Resolved and discarded incidents are final.")
        db.execute("UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?", (status, datetime.now(timezone.utc).isoformat(), incident_id))
        return dict(db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone())


def summary():
    with connection() as db:
        result = {"total": db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]}
        for field, values in (("status", STATUSES), ("category", CATEGORIES), ("origin", ORIGINS), ("branch", BRANCHES)):
            counts = dict.fromkeys(values, 0)
            counts.update({row[0]: row[1] for row in db.execute(f"SELECT {field}, COUNT(*) FROM incidents GROUP BY {field}")})
            result[f"by_{field}"] = counts
        return result