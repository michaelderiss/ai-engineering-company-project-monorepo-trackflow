"""Agent graph evaluations against the existing TrackFlow RAG pipeline."""

from __future__ import annotations

import time
from unittest.mock import patch

from services.agent.graph import get_compiled_graph, run_agent
from services.agent.tools import TicketLookupOutput, lookup_ticket


@patch("services.agent.graph.generate_answer")
@patch("services.agent.graph.retrieve")
def test_empty_question_stops_before_retrieval(mock_retrieve, mock_generate):
    result = run_agent("   ")

    mock_retrieve.assert_not_called()
    mock_generate.assert_not_called()
    assert result["error"] == "Question must not be empty."
    assert [entry["node"] for entry in result["trace"]["nodes"]] == [
        "receive",
        "empty_error",
    ]
    assert result["trace"]["status"] == "failed"


@patch("services.agent.graph.generate_answer")
@patch("services.agent.graph.retrieve")
def test_retrieval_runs_before_generation(mock_retrieve, mock_generate):
    chunk = {
        "source_document": "returns-policy",
        "section": "Standard Return Window",
        "text": "Eligible returns have a 30-day window.",
    }
    mock_retrieve.return_value = [chunk]
    mock_generate.return_value = "TrackFlow allows 30 days for eligible returns."

    result = run_agent("What is the return window?")

    mock_retrieve.assert_called_once_with("What is the return window?")
    mock_generate.assert_called_once_with(
        "What is the return window?",
        [chunk],
    )
    assert [entry["node"] for entry in result["trace"]["nodes"]] == [
        "receive",
        "classify",
        "retrieve",
        "generate",
    ]
    assert result["answer"] == "TrackFlow allows 30 days for eligible returns."


@patch("services.agent.graph.generate_answer")
@patch("services.agent.graph.retrieve")
def test_no_context_routes_to_honest_answer(mock_retrieve, mock_generate):
    mock_retrieve.return_value = []

    result = run_agent("Tell me about a policy not in the knowledge base.")

    mock_generate.assert_not_called()
    assert [entry["node"] for entry in result["trace"]["nodes"]] == [
        "receive",
        "classify",
        "retrieve",
        "no_context",
    ]
    assert "knowledge base" in result["answer"]


@patch("services.agent.graph.generate_answer")
@patch("services.agent.graph.retrieve")
def test_answer_is_grounded_in_retrieved_returns_policy(mock_retrieve, mock_generate):
    grounded_chunk = {
        "source_document": "returns-policy",
        "section": "Standard Return Window",
        "text": "TrackFlow offers a 30-day return window for eligible products.",
    }
    mock_retrieve.return_value = [grounded_chunk]
    mock_generate.side_effect = lambda question, context: (
        f"Based on {context[0]['source_document']}: "
        "eligible products have a 30-day return window."
    )

    result = run_agent("What is the TrackFlow return window?")

    assert "30-day" in result["answer"]
    assert "returns-policy" in result["answer"]
    assert result["trace"]["status"] == "completed"
    assert result["trace"]["checkpoints"]


def test_graph_is_compiled_before_execution():
    graph = get_compiled_graph()

    assert graph is not None


@patch("services.agent.graph.lookup_ticket")
@patch("services.agent.graph.retrieve")
@patch("services.agent.graph.generate_answer")
def test_ticket_question_routes_to_ticket_tool_only(
    mock_generate,
    mock_retrieve,
    mock_lookup,
):
    mock_lookup.return_value = TicketLookupOutput(
        found=True,
        ticket_id=482,
        status="in_progress",
        category="carrier_issue",
        title="Parcel delayed",
    )

    result = run_agent("What is the status of ticket 482?")

    mock_lookup.assert_called_once_with(482)
    mock_retrieve.assert_not_called()
    mock_generate.assert_not_called()
    assert [entry["node"] for entry in result["trace"]["nodes"]] == [
        "receive",
        "classify",
        "ticket_lookup",
        "ticket_answer",
    ]
    assert "in_progress" in result["answer"]
    assert "ticket" in result["trace"]["checkpoints"][-1]["sources"]


@patch("services.agent.graph.lookup_ticket")
@patch("services.agent.graph.retrieve")
@patch("services.agent.graph.generate_answer")
def test_policy_question_routes_to_rag_only(
    mock_generate,
    mock_retrieve,
    mock_lookup,
):
    chunk = {
        "source_document": "returns-policy",
        "section": "Standard Return Window",
        "text": "Eligible products have a 30-day return window.",
    }
    mock_retrieve.return_value = [chunk]
    mock_generate.return_value = "The policy allows 30 days."

    result = run_agent("What is the standard return policy?")

    mock_lookup.assert_not_called()
    mock_retrieve.assert_called_once_with("What is the standard return policy?")
    mock_generate.assert_called_once()
    assert [entry["node"] for entry in result["trace"]["nodes"]] == [
        "receive",
        "classify",
        "retrieve",
        "generate",
    ]
    assert "rag" in result["trace"]["checkpoints"][-1]["sources"]


@patch("services.agent.graph.lookup_ticket")
@patch("services.agent.graph.retrieve")
def test_ticket_not_found_has_honest_fallback(mock_retrieve, mock_lookup):
    mock_lookup.return_value = TicketLookupOutput(
        found=False,
        ticket_id=999,
        fallback="not_found",
    )

    result = run_agent("Can you show ticket 999?")

    mock_retrieve.assert_not_called()
    assert result["answer"] == "I couldn't confirm that ticket's status right now."
    assert result["trace"]["nodes"][-1]["node"] == "ticket_answer"


@patch("services.agent.tools.incident_store.get_incident")
def test_ticket_tool_returns_not_found_contract(mock_get_incident):
    mock_get_incident.return_value = None

    output = lookup_ticket(999)

    mock_get_incident.assert_called_once_with(999)
    assert output.found is False
    assert output.fallback == "not_found"


@patch("services.agent.tools.incident_store.get_incident")
def test_ticket_tool_times_out_with_numeric_fallback(mock_get_incident):
    mock_get_incident.side_effect = lambda ticket_id: time.sleep(3.2)

    started = time.monotonic()
    output = lookup_ticket(482)
    elapsed = time.monotonic() - started

    assert output.found is False
    assert output.fallback == "timeout"
    assert elapsed < 3.5
