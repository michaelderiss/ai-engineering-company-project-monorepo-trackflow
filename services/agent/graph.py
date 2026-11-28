"""Explicit LangGraph flow over the existing TrackFlow RAG functions."""

from __future__ import annotations

import threading
import uuid
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from data.pipelines.rag import generate_answer, retrieve


class AgentState(TypedDict, total=False):
    """Minimum state needed by the graph nodes."""

    question: str
    context: list[dict[str, Any]]
    answer: str
    error: str


class AgentExecutionError(RuntimeError):
    """Safe, user-facing agent execution failure."""


class AgentGraphBuildError(RuntimeError):
    """Graph compilation or structural configuration failure."""


_lock = threading.Lock()
_traces: dict[str, dict[str, Any]] = {}
_checkpointer = MemorySaver()


def receive_question(state: AgentState) -> AgentState:
    question = str(state.get("question") or "").strip()
    return {"question": question, "context": [], "answer": "", "error": ""}


def retrieve_context(state: AgentState) -> AgentState:
    question = state["question"]
    try:
        context = retrieve(question)
    except Exception as exc:
        raise AgentExecutionError("The knowledge base could not be searched.") from exc
    return {"context": context}


def generate_grounded_answer(state: AgentState) -> AgentState:
    try:
        answer = generate_answer(state["question"], state["context"])
    except Exception as exc:
        raise AgentExecutionError("The answer could not be generated.") from exc
    return {"answer": answer}


def answer_without_context(state: AgentState) -> AgentState:
    return {
        "answer": "I don't have enough information in our knowledge base to answer that.",
    }


def reject_empty_question(state: AgentState) -> AgentState:
    return {
        "answer": "",
        "error": "Question must not be empty.",
    }


def route_after_receive(state: AgentState) -> Literal["retrieve", "empty_error"]:
    return "retrieve" if state["question"] else "empty_error"


def route_after_retrieve(state: AgentState) -> Literal["generate", "no_context"]:
    return "generate" if state["context"] else "no_context"


def build_agent_graph(checkpointer: MemorySaver | None = None):
    """Build and compile the graph; compilation happens before execution."""

    graph = StateGraph(AgentState)
    graph.add_node("receive", receive_question)
    graph.add_node("retrieve", retrieve_context)
    graph.add_node("generate", generate_grounded_answer)
    graph.add_node("no_context", answer_without_context)
    graph.add_node("empty_error", reject_empty_question)

    graph.add_edge(START, "receive")
    graph.add_conditional_edges(
        "receive",
        route_after_receive,
        {"retrieve": "retrieve", "empty_error": "empty_error"},
    )
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"generate": "generate", "no_context": "no_context"},
    )
    graph.add_edge("generate", END)
    graph.add_edge("no_context", END)
    graph.add_edge("empty_error", END)

    try:
        return graph.compile(checkpointer=checkpointer or _checkpointer)
    except Exception as exc:
        raise AgentGraphBuildError("Agent graph structure is invalid.") from exc


_compiled_graph = build_agent_graph()


def get_compiled_graph():
    """Return the compiled graph used by the API and evals."""

    return _compiled_graph


def run_agent(question: str) -> dict[str, Any]:
    """Execute one graph run and persist a structured trace and checkpoints."""

    run_id = str(uuid.uuid4())
    thread_id = f"agent-{run_id}"
    config = {"configurable": {"thread_id": thread_id}}
    trace: dict[str, Any] = {
        "run_id": run_id,
        "thread_id": thread_id,
        "status": "running",
        "nodes": [],
        "answer": "",
        "error": "",
    }

    try:
        final_state: dict[str, Any] = {}
        for update in _compiled_graph.stream(
            {"question": question},
            config=config,
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue
            for node_name, node_output in update.items():
                node_output = dict(node_output) if isinstance(node_output, dict) else {}
                final_state.update(node_output)
                trace["nodes"].append(
                    {
                        "node": node_name,
                        "output": {
                            key: value
                            for key, value in node_output.items()
                            if key in {"question", "answer", "error"}
                        },
                    }
                )

        trace["answer"] = str(final_state.get("answer") or "")
        trace["error"] = str(final_state.get("error") or "")
        trace["status"] = "failed" if trace["error"] else "completed"
    except AgentExecutionError as exc:
        trace["status"] = "failed"
        trace["error"] = str(exc)
    except Exception as exc:
        trace["status"] = "failed"
        trace["error"] = "Agent execution failed."
        raise AgentExecutionError(trace["error"]) from exc
    finally:
        checkpoints = [
            snapshot.values
            for snapshot in _compiled_graph.get_state_history(config)
        ]
        trace["checkpoints"] = checkpoints
        with _lock:
            _traces[run_id] = trace

    return {
        "run_id": run_id,
        "answer": trace["answer"],
        "error": trace["error"],
        "trace": trace,
    }


def get_trace(run_id: str) -> dict[str, Any] | None:
    with _lock:
        trace = _traces.get(run_id)
        return dict(trace) if trace else None


def get_checkpoint_history(run_id: str) -> list[dict[str, Any]]:
    with _lock:
        trace = _traces.get(run_id)
    if not trace:
        return []

    config = {"configurable": {"thread_id": trace["thread_id"]}}
    return [
        dict(snapshot.values)
        for snapshot in _compiled_graph.get_state_history(config)
    ]
