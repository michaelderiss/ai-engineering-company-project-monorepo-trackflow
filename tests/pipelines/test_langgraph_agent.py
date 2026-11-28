"""Agent graph evaluations against the existing TrackFlow RAG pipeline."""

from __future__ import annotations

from unittest.mock import patch

from services.agent.graph import get_compiled_graph, run_agent


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
