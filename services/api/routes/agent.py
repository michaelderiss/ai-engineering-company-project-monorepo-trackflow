"""FastAPI boundary for the compiled LangGraph agent."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.agent import (
    AgentExecutionError,
    get_trace,
    run_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Question to answer from the TrackFlow knowledge base.")


class AgentQueryResponse(BaseModel):
    run_id: str
    answer: str


class TraceResponse(BaseModel):
    run_id: str
    thread_id: str
    status: str
    nodes: list[dict]
    answer: str
    error: str
    checkpoints: list[dict]


@router.post("/query", response_model=AgentQueryResponse)
def agent_query(payload: AgentQueryRequest) -> AgentQueryResponse:
    try:
        result = run_agent(payload.question)
    except AgentExecutionError as exc:
        logger.warning("Agent execution failed: %s", exc)
        raise HTTPException(status_code=500, detail="Agent query could not be completed.") from exc

    if result["error"]:
        raise HTTPException(status_code=400, detail=result["error"])

    logger.info("Agent query completed run_id=%s", result["run_id"])
    return AgentQueryResponse(run_id=result["run_id"], answer=result["answer"])


@router.get("/traces/{run_id}", response_model=TraceResponse)
def agent_trace(run_id: str) -> TraceResponse:
    trace = get_trace(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return TraceResponse(**trace)
