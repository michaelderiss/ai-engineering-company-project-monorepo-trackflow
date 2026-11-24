"""
Milestone 7 — RAG Pipeline
=============================
Phase 2 — Retrieval and generation pipeline.

Functions (single-responsibility, externally callable):
  1. retrieve(query, *, k, min_score) → list[dict]   (Qdrant search, filtered)
  2. generate_answer(question, context) → str          (prompt assembly + LLM)
  3. query(question) → str                            (orchestrator: retrieve + generate)

The ``query`` function is the only public entrypoint external consumers should
call.  ``retrieve`` and ``generate_answer`` are also exported so that a future
LangGraph agent can call them as separate steps without duplicating logic.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI

from data.process.rag import COLLECTION_NAME, EMBEDDING_DIM, embed

__all__ = ["retrieve", "generate_answer", "query"]

# ---------------------------------------------------------------------------
# Similarity threshold
# ---------------------------------------------------------------------------

# Cosine similarity threshold. Points below this score are treated as "not
# relevant".  We chose 0.45 because:
#   - text-embedding-3-small produces embeddings in the [−1, 1] range.
#   - Domain-specific policy text is fairly dense; semantically unrelated
#     queries typically score < 0.35.
#   - Manual testing on the 8 eval queries showed that 0.45 reliably filters
#     out false positives while keeping the correct chunk in the top 3.
MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))


def _get_qdrant_client():
    """Return a Qdrant client — local or cloud based on env."""
    from qdrant_client import QdrantClient

    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    location = os.getenv("QDRANT_LOCATION", ":memory:")

    if url:
        return QdrantClient(url=url, api_key=api_key or None)
    return QdrantClient(location=location)


# ---------------------------------------------------------------------------
# Retriever
# ---------------------------------------------------------------------------

def retrieve(
    question: str,
    *,
    k: int = 5,
    min_score: float = MIN_SIMILARITY,
) -> list[dict[str, Any]]:
    """Embed *question*, search Qdrant for the top-*k* nearest neighbours,
    filter out any hit below *min_score*, and return the surviving payloads
    (raw Qdrant SDK objects are never returned).

    Parameters
    ----------
    question:
        The user's natural-language question.
    k:
        Maximum number of neighbours to fetch from Qdrant.
    min_score:
        Minimum cosine-similarity score for a hit to be considered relevant.

    Returns
    -------
    list[dict]:
        Each dict contains the Qdrant payload fields (source_document, section,
        text, company, language, chunk_index).  Empty list if nothing is above
        the threshold.
    """
    client = _get_qdrant_client()
    query_vector = embed(question)

    # Try searching — if the collection doesn't exist, return empty
    try:
        search_result = client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=k,
            with_payload=True,
        )
    except Exception:
        return []

    # Filter by min_score and return only payloads (no raw SDK objects)
    results: list[dict[str, Any]] = []
    for scored_point in search_result:
        if scored_point.score >= min_score:
            results.append(dict(scored_point.payload or {}))

    return results


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------

# Generation model — deliberately DIFFERENT from the embedding model.
GENERATION_MODEL = os.getenv(
    "RAG_GENERATION_MODEL",
    "gpt-4o-mini",  # 4Geeks-provided generation model (chat/completions)
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


def _build_system_prompt() -> str:
    """System prompt that instructs the model to answer in the voice and
    audience defined in the M7 BRIEFING: a TrackFlow salesperson speaking
    to a prospect or client.

    The answer must:
      - Use only the retrieved context — never invent facts.
      - Never promise delivery SLAs during high-demand dates.
      - Never describe international returns as "automatic".
      - Never offer a storage discount without mentioning Miguel Torres's approval.
      - If no context is available, state that there isn't enough information.
    """
    return (
        "You are a TrackFlow salesperson speaking with a prospect or client. "
        "Answer concisely and professionally, using only the provided context "
        "from TrackFlow's internal knowledge base.\n\n"
        "RULES:\n"
        "1. Use ONLY the context below — never make up numbers, policies, or terms.\n"
        "2. NEVER promise a delivery SLA during declared high-demand dates "
        "(Black Friday, Cyber Monday, Christmas season Nov 15–Jan 10). "
        "Reference the seasonal delay policy instead.\n"
        "3. NEVER describe international returns as \"automatic\". "
        "International returns always require manual handling.\n"
        "4. NEVER offer a storage discount above 10% without stating that it "
        "requires Miguel Torres's (Commercial Director) approval.\n"
        "5. If the context contains no relevant information, say: "
        "\"I don't have enough information in our knowledge base to answer that.\"\n"
        "6. Always cite the source document name when providing specific "
        "numbers, rates, or timeframes.\n"
        "7. Be helpful and clear, as you would on a call with a client."
    )


def generate_answer(question: str, context: list[dict[str, Any]]) -> str:
    """Assemble a prompt from *question* and retrieved *context* chunks, call
    the generation LLM, and return the final answer string.

    Parameters
    ----------
    question:
        The user's original question.
    context:
        The list of payload dicts returned by ``retrieve()``.  May be empty.

    Returns
    -------
    str:
        The model-generated answer.
    """
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    # Build context block from retrieved chunks
    if not context:
        context_block = "No relevant documents were found in the knowledge base."
    else:
        lines: list[str] = []
        for i, chunk in enumerate(context):
            source = chunk.get("source_document", "unknown")
            section = chunk.get("section", "")
            text = chunk.get("text", "")
            header = f"--- Document {i + 1}: {source}"
            if section:
                header += f" / {section}"
            lines.append(header)
            lines.append(text)
        context_block = "\n\n".join(lines)

    messages = [
        {"role": "system", "content": _build_system_prompt()},
        {"role": "user", "content": f"CONTEXT:\n{context_block}\n\nQUESTION: {question}"},
    ]

    resp = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
        temperature=0.2,  # Low temperature for faithful answers
        max_tokens=1024,
    )

    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Query — the only public entrypoint
# ---------------------------------------------------------------------------

def query(question: str) -> str:
    """Orchestrator: ``retrieve()`` + ``generate_answer()``.

    This is the only function external consumers should call.  It is
    deliberately factored as a composition of two independent steps so that
    a future LangGraph agent can call ``retrieve()`` and ``generate_answer()``
    separately without repeating work.
    """
    context = retrieve(question)
    return generate_answer(question, context)
