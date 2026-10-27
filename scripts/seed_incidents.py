from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from packages.shared.incident_validation import validate_csv_row
from packages.shared.incidents import CSV_BRANCHES, CSV_CATEGORIES, CSV_STATUSES, IncidentCreate
from services.api.incidents import create_incident


def seed_incidents(path: Path) -> dict[str, int]:
    counts = {"inserted": 0, "skipped": 0, "invalid": 0}
    with path.open(encoding="utf-8-sig", newline="") as source:
        for line, row in enumerate(csv.DictReader(source), start=2):
            reasons = validate_csv_row(row)
            if reasons:
                counts["invalid"] += 1
                print(f"Row {line} skipped: {', '.join(reasons)}")
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
                print(f"Row {line} skipped: invalid title, date, or mapping")
                continue
            source_id = (row.get("incident_id") or "").strip()
            source_key = "csv:" + source_id if source_id else "fallback:" + hashlib.sha256(f"{title}|{created_at}".encode()).hexdigest()
            record = create_incident(payload, created_at=created_at, source_key=source_key)
            counts["inserted" if record else "skipped"] += 1
    print(f"Inserted: {counts['inserted']}; duplicates skipped: {counts['skipped']}; invalid: {counts['invalid']}")
    return counts


def main():
    parser = argparse.ArgumentParser(description="Load historical TrackFlow customer incidents once.")
    parser.add_argument("csv", nargs="?", type=Path, default=ROOT / "scripts" / "incidents-trackflow.csv")
    args = parser.parse_args()
    try:
        seed_incidents(args.csv)
    except (OSError, csv.Error):
        parser.exit(1, "Could not read the CSV. Check the file path, permissions, and CSV format.\n")


if __name__ == "__main__":
    main()