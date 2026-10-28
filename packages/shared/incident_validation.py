from __future__ import annotations

import csv
from io import StringIO

VALID_COUNTRIES = {"US", "ES"}
VALID_CARRIERS_BY_COUNTRY = {
    "US": {"UPS", "FEDEX", "DHL_US"},
    "ES": {"MRW", "SEUR", "DHL_ES", "LOCAL_ES"},
}
VALID_CATEGORIES = ["LOST_PARCEL", "DELAYED_DELIVERY", "WRONG_ADDRESS", "RETURN_REQUEST", "DAMAGE"]
VALID_STATUS = ["OPEN", "CLOSED", "DISCARDED"]
REQUIRED_COLUMNS = {"date", "country", "carrier", "tracking_number", "category", "description", "status", "customer_email"}


def validate_csv_headers(fieldnames):
    if not fieldnames or not REQUIRED_COLUMNS.issubset(fieldnames):
        raise ValueError("The CSV is missing required columns.")
    if len(fieldnames) != len(set(fieldnames)):
        raise ValueError("The CSV contains duplicate columns.")


def parse_csv_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text), strict=True)
    validate_csv_headers(reader.fieldnames)
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError("The CSV format is invalid.") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("The CSV contains rows with an unexpected number of columns.")
    return [{key: value or "" for key, value in row.items()} for row in rows]


def clean(value: str | None) -> str:
    return "" if value is None else value.strip()


def safe_int(value: str | None) -> int | None:
    try:
        return int(clean(value))
    except ValueError:
        return None


def validate_csv_row(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    country = clean(row.get("country"))
    carrier = clean(row.get("carrier"))
    status = clean(row.get("status"))
    score = safe_int(row.get("satisfaction_score"))
    if country not in VALID_COUNTRIES:
        reasons.append("invalid_country")
    if country not in VALID_COUNTRIES or carrier not in VALID_CARRIERS_BY_COUNTRY[country]:
        reasons.append("invalid_carrier")
    if len(clean(row.get("tracking_number"))) < 8:
        reasons.append("invalid_tracking_number")
    if clean(row.get("category")) not in VALID_CATEGORIES:
        reasons.append("invalid_category")
    if len(clean(row.get("description"))) < 5:
        reasons.append("invalid_description")
    if "@" not in clean(row.get("customer_email")):
        reasons.append("invalid_email")
    if status not in VALID_STATUS:
        reasons.append("invalid_status")
    if status == "CLOSED" and score is None:
        reasons.append("closed_without_score")
    if score is not None and not 1 <= score <= 5:
        reasons.append("invalid_score_range")
    return reasons