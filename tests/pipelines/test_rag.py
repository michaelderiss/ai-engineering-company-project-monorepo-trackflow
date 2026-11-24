"""
Milestone 7 — RAG Knowledge Base
==================================
Phase 5 — Unit tests for retrieve() and query().

Tests use mocked Qdrant client and mocked LLM — no live services required.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock, ANY
import json
from pathlib import Path

import pytest

from data.pipelines.rag import retrieve, query, generate_answer, MIN_SIMILARITY


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_chunks() -> list[dict]:
    """Simulated Qdrant payloads as they would be returned from the store."""
    return [
        {
            "source_document": "sla-delivery",
            "section": "Standard Delivery Timeframes",
            "company": "trackflow",
            "language": "en",
            "chunk_index": 0,
            "text": "TrackFlow offers Standard 2–4 business days delivery for continental USA.",
        },
        {
            "source_document": "returns-policy",
            "section": "Standard Return Window",
            "company": "trackflow",
            "language": "en",
            "chunk_index": 0,
            "text": "TrackFlow offers a 30-day return window for all eligible products.",
        },
        {
            "source_document": "carrier-coverage",
            "section": "Nacex",
            "company": "trackflow",
            "language": "en",
            "chunk_index": 2,
            "text": "Nacex covers Aragón y zona norte at €4.60 per shipment.",
        },
    ]


@pytest.fixture
def mock_qdrant_search() -> MagicMock:
    """Create a mock for QdrantClient.search() return value.

    Uses a simple fake class instead of ScoredPoint spec to avoid
    import/attribute issues in the mock setup.
    """
    class FakeScoredPoint:
        def __init__(self, score: float, payload: dict):
            self.score = score
            self.payload = payload

    def _make(score: float, payload: dict) -> FakeScoredPoint:
        return FakeScoredPoint(score, payload)

    return _make


# ---------------------------------------------------------------------------
# retrieve() tests
# ---------------------------------------------------------------------------

@patch("data.pipelines.rag._get_qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_filters_below_min_score(
    mock_embed: MagicMock,
    mock_get_client: MagicMock,
    sample_chunks: list[dict],
    mock_qdrant_search: MagicMock,
):
    """Results below min_score are excluded."""
    mock_embed.return_value = [0.1] * 1536

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [
        MagicMock(name="trackflow_knowledge")
    ]

    # Create scored points: first two above threshold, third below
    above = mock_qdrant_search(0.85, sample_chunks[0])
    also_above = mock_qdrant_search(0.72, sample_chunks[1])
    below = mock_qdrant_search(0.30, sample_chunks[2])

    mock_client.search.return_value = [above, also_above, below]
    mock_get_client.return_value = mock_client

    results = retrieve("test question")

    assert len(results) == 2
    assert results[0]["source_document"] == "sla-delivery"
    assert results[1]["source_document"] == "returns-policy"


@patch("data.pipelines.rag._get_qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_fewer_than_k_results(
    mock_embed: MagicMock,
    mock_get_client: MagicMock,
    sample_chunks: list[dict],
    mock_qdrant_search: MagicMock,
):
    """When fewer than k results pass the threshold, only those are returned."""
    mock_embed.return_value = [0.1] * 1536

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [
        MagicMock(name="trackflow_knowledge")
    ]
    above = mock_qdrant_search(0.91, sample_chunks[0])
    mock_client.search.return_value = [above]
    mock_get_client.return_value = mock_client

    results = retrieve("test", k=5)

    assert len(results) == 1
    assert results[0]["source_document"] == "sla-delivery"


@patch("data.pipelines.rag._get_qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_returns_empty_when_all_below_threshold(
    mock_embed: MagicMock,
    mock_get_client: MagicMock,
    sample_chunks: list[dict],
    mock_qdrant_search: MagicMock,
):
    """When all results are below min_score, return empty list."""
    mock_embed.return_value = [0.1] * 1536

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [
        MagicMock(name="trackflow_knowledge")
    ]
    low1 = mock_qdrant_search(0.25, sample_chunks[0])
    low2 = mock_qdrant_search(0.30, sample_chunks[1])
    mock_client.search.return_value = [low1, low2]
    mock_get_client.return_value = mock_client

    results = retrieve("unrelated question")

    assert len(results) == 0


# ---------------------------------------------------------------------------
# retrieve() with custom min_score
# ---------------------------------------------------------------------------

@patch("data.pipelines.rag._get_qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_custom_min_score(
    mock_embed: MagicMock,
    mock_get_client: MagicMock,
    sample_chunks: list[dict],
    mock_qdrant_search: MagicMock,
):
    """Custom min_score parameter is respected."""
    mock_embed.return_value = [0.1] * 1536

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = [
        MagicMock(name="trackflow_knowledge")
    ]
    marginal = mock_qdrant_search(0.50, sample_chunks[0])
    mock_client.search.return_value = [marginal]
    mock_get_client.return_value = mock_client

    # With default threshold 0.45, this should be included
    results = retrieve("test", min_score=0.45)
    assert len(results) == 1

    # With a higher threshold 0.60, this should be excluded
    results2 = retrieve("test", min_score=0.60)
    assert len(results2) == 0


# ---------------------------------------------------------------------------
# retrieve() tests: non-existent collection
# ---------------------------------------------------------------------------

@patch("data.pipelines.rag._get_qdrant_client")
@patch("data.pipelines.rag.embed")
def test_retrieve_no_collection(
    mock_embed: MagicMock,
    mock_get_client: MagicMock,
):
    """If the collection doesn't exist yet, return empty list."""
    mock_embed.return_value = [0.1] * 1536

    mock_client = MagicMock()
    mock_client.get_collections.return_value.collections = []
    mock_get_client.return_value = mock_client

    results = retrieve("anything")

    assert len(results) == 0


# ---------------------------------------------------------------------------
# generate_answer() tests
# ---------------------------------------------------------------------------

@patch("data.pipelines.rag.OpenAI")
def test_generate_answer_returns_model_output(
    mock_openai: MagicMock,
    sample_chunks: list[dict],
):
    """generate_answer() returns the model output, not raw chunks."""
    mock_instance = MagicMock()
    mock_instance.chat.completions.create.return_value.choices[0].message.content = (
            "TrackFlow gives customers a full 30 days from delivery to initiate a return."
    )
    mock_openai.return_value = mock_instance

    answer = generate_answer("What is the return window?", sample_chunks[1:2])

    assert isinstance(answer, str)
    assert "30 days" in answer
    # Verify the model output is genuinely the model's (mocked) reply,
    # not just the raw chunk text echoed back unchanged.
    assert answer != sample_chunks[1]["text"]


@patch("data.pipelines.rag.OpenAI")
def test_generate_answer_empty_context(
    mock_openai: MagicMock,
):
    """With no context, the model responds honestly about lacking info."""
    mock_instance = MagicMock()
    mock_instance.chat.completions.create.return_value.choices[0].message.content = (
        "I don't have enough information in our knowledge base to answer that."
    )
    mock_openai.return_value = mock_instance

    answer = generate_answer("Some unknown question", [])

    assert isinstance(answer, str)
    assert len(answer) > 0


# ---------------------------------------------------------------------------
# query() tests (integration of retrieve + generate_answer)
# ---------------------------------------------------------------------------

@patch("data.pipelines.rag.retrieve")
@patch("data.pipelines.rag.generate_answer")
def test_query_returns_generated_output_not_raw_chunks(
    mock_generate: MagicMock,
    mock_retrieve: MagicMock,
    sample_chunks: list[dict],
):
    """query() returns the model-generated string, not raw chunk text."""
    mock_retrieve.return_value = [sample_chunks[1]]
    mock_generate.return_value = "TrackFlow offers a 30-day return window."

    answer = query("return window?")

    assert answer == "TrackFlow offers a 30-day return window."
    mock_retrieve.assert_called_once_with("return window?")
    mock_generate.assert_called_once_with("return window?", [sample_chunks[1]])


@patch("data.pipelines.rag.retrieve")
@patch("data.pipelines.rag.generate_answer")
def test_query_uses_retrieve_and_generate_answer(
    mock_generate: MagicMock,
    mock_retrieve: MagicMock,
):
    """query() is literally retrieve() + generate_answer()."""
    mock_retrieve.return_value = []
    mock_generate.return_value = "No information available."

    answer = query("something unknown")

    assert answer == "No information available."
    mock_retrieve.assert_called_once()
    mock_generate.assert_called_once()


# ---------------------------------------------------------------------------
# Domain structure validation
# ---------------------------------------------------------------------------

def test_domain_payload_structure(sample_chunks: list[dict]):
    """Verify that chunks follow the required domain data structure."""
    required_fields = {"source_document", "section", "company", "language", "chunk_index", "text"}
    for chunk in sample_chunks:
        assert required_fields.issubset(chunk.keys()), f"Missing fields: {required_fields - chunk.keys()}"
        assert chunk["company"] == "trackflow"
        assert chunk["language"] == "en"
        assert isinstance(chunk["chunk_index"], int)


# ---------------------------------------------------------------------------
# Eval: test-queries.json loads correctly
# ---------------------------------------------------------------------------

def test_eval_queries_file_exists():
    """data/eval/test-queries.json exists with at least 8 questions."""
    eval_path = Path(__file__).resolve().parents[2] / "data" / "eval" / "test-queries.json"
    assert eval_path.is_file(), f"File not found: {eval_path}"

    with open(eval_path, encoding="utf-8") as f:
        queries = json.load(f)

    assert len(queries) >= 8, f"Expected at least 8 queries, got {len(queries)}"

    documents_covered: set[str] = set()
    for q in queries:
        assert "question" in q
        assert "expected_document" in q
        documents_covered.add(q["expected_document"])

    expected_docs = {"sla-delivery", "returns-policy", "carrier-coverage", "storage-pricing"}
    assert documents_covered == expected_docs, (
        f"Not all documents covered. Missing: {expected_docs - documents_covered}"
    )
