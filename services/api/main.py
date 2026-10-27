from __future__ import annotations

import csv
import logging
from io import StringIO
from pathlib import Path
import sys

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.incidents_analysis import (  # noqa: E402
    AnalysisResult,
    analyze_incidents_text,
    build_export_rows,
)
from services.api.auth import get_current_user  # noqa: E402
from services.api.database import seed_suppliers, seed_users  # noqa: E402
from services.api.models import User  # noqa: E402
from services.api.routes.auth import router as auth_router  # noqa: E402
from services.api.routes.profiles import router as profiles_router  # noqa: E402
from services.api.routes.suppliers import router as suppliers_router  # noqa: E402
from services.api.routes.users import router as users_router  # noqa: E402
from services.api.routes.incidents import router as incidents_router  # noqa: E402

app = FastAPI(title="TrackFlow API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_LAST_ANALYSIS: dict | None = None


@app.on_event("startup")
def ensure_seed_data() -> None:
    seed_suppliers()
    seed_users()


app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profiles_router)
app.include_router(suppliers_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/incidents/analyze")
async def analyze_incidents(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    global _LAST_ANALYSIS

    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted.")

    try:
        raw_bytes = await file.read()
        csv_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid encoding. CSV must be UTF-8.",
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"Could not read file: {exc}") from exc

    try:
        result = analyze_incidents_text(csv_text)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CSV structure or values: {exc}",
        ) from exc

    payload = result.to_dict()
    payload["source_file"] = file.filename or "uploaded.csv"
    _LAST_ANALYSIS = payload
    return payload


@app.get("/api/incidents/results/export")
def export_last_results(current_user: User = Depends(get_current_user)) -> StreamingResponse:
    if _LAST_ANALYSIS is None:
        raise HTTPException(status_code=404, detail="No analysis available. Upload a CSV first.")

    result_dict = dict(_LAST_ANALYSIS)
    result_obj = AnalysisResult(
        total_records=result_dict["total_records"],
        valid_records=result_dict["valid_records"],
        invalid_records=result_dict["invalid_records"],
        invalid_breakdown=result_dict["invalid_breakdown"],
        category_breakdown=result_dict["category_breakdown"],
        status_breakdown=result_dict["status_breakdown"],
        country_breakdown=result_dict["country_breakdown"],
        satisfaction_breakdown={
            int(k): v for k, v in result_dict["satisfaction_breakdown"].items()
        },
        satisfaction_average=result_dict["satisfaction_average"],
        scored_closed_incidents=result_dict["scored_closed_incidents"],
        closed_incidents=result_dict["closed_incidents"],
    )
    export_rows = build_export_rows(result_obj)

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["section", "metric", "value", "percentage"],
    )
    writer.writeheader()
    writer.writerows(export_rows)

    csv_body = output.getvalue()
    return StreamingResponse(
        iter([csv_body]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=results.csv"},
    )


app.include_router(incidents_router)


def is_manager_request(request):
    path = request.url.path
    return path.startswith("/api/incidents") and path not in (
        "/api/incidents/analyze", "/api/incidents/results/export",
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    if not is_manager_request(request):
        return await request_validation_exception_handler(request, exc)
    errors = {}
    for error in exc.errors():
        field = str(error["loc"][-1])
        if error["type"] == "value_error.missing":
            message = "This field is required."
        elif error["type"] == "value_error.const":
            message = "Please choose an available option."
        elif "min_length" in error["type"]:
            message = "Please enter a value."
        elif "max_length" in error["type"]:
            message = "Please use 120 characters or fewer."
        else:
            message = "Please enter a valid value."
        errors[field] = message
    return JSONResponse({"message": "Please check the highlighted fields.", "errors": errors}, status_code=400)


@app.exception_handler(Exception)
async def unexpected_exception_handler(request, exc):
    logging.getLogger(__name__).error("API request failed", exc_info=exc)
    return JSONResponse({"message": "Something went wrong. Please try again."}, status_code=500)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    if is_manager_request(request):
        if isinstance(exc.detail, dict):
            return JSONResponse({"message": "Please check the highlighted fields.", "errors": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return JSONResponse({"message": str(exc.detail)}, status_code=exc.status_code, headers=exc.headers)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
