from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.shared.incident_validation import parse_csv_rows, validate_csv_row
from packages.shared.incidents import CSV_BRANCHES, CSV_CATEGORIES, CSV_STATUSES, IncidentCreate
from services.api.incidents import create_incident


class SeedInputError(ValueError):
    pass


class SeedStorageError(RuntimeError):
    pass


def seed_incidents(path: Path) -> dict[str, int]:
    counts = {"inserted": 0, "skipped": 0, "invalid": 0}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise SeedInputError("Could not read the CSV. Check the path, permissions, and UTF-8 encoding.") from exc
    try:
        rows = parse_csv_rows(text)
    except (ValueError, csv.Error) as exc:
        raise SeedInputError("The CSV structure is invalid. Check the required columns and try again.") from exc
    for line, row in enumerate(rows, start=2):
        reasons = validate_csv_row(row)
        if reasons:
            counts["invalid"] += 1
            print(f"Row {line} skipped: {', '.join(reasons)}", file=sys.stderr)
            continue
        try:
            description = row["description"]
            title = description[:120].strip()
            created_at = datetime.strptime(row["date"].strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
            payload = IncidentCreate(
                title=title, description=description, origin="customer",
                status=CSV_STATUSES[row["status"].strip()],
                category=CSV_CATEGORIES[row["category"].strip()],
                branch=CSV_BRANCHES[row["country"].strip()],
            )
        except (KeyError, ValueError, TypeError):
            counts["invalid"] += 1
            print(f"Row {line} skipped: invalid title, date, or mapping", file=sys.stderr)
            continue
        source_id = (row.get("incident_id") or "").strip()
        source_key = "csv:" + source_id if source_id else "fallback:" + hashlib.sha256(f"{title}|{created_at}".encode()).hexdigest()
        try:
            record = create_incident(payload, created_at=created_at, source_key=source_key)
        except (sqlite3.Error, OSError) as exc:
            raise SeedStorageError("Could not save incidents. Check database access and retry; previously imported rows will not be duplicated.") from exc
        counts["inserted" if record else "skipped"] += 1
    print(f"Inserted: {counts['inserted']}; duplicates skipped: {counts['skipped']}; invalid: {counts['invalid']}")
    return counts


def main():
    parser = argparse.ArgumentParser(description="Load historical TrackFlow customer incidents once.")
    parser.add_argument("csv", nargs="?", type=Path, default=ROOT / "scripts" / "incidents-trackflow.csv")
    args = parser.parse_args()
    try:
        seed_incidents(args.csv)
    except (SeedInputError, SeedStorageError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()