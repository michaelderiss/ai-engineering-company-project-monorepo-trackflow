"""
Milestone 7 — RAG Knowledge Base
==================================
Phase 1 — Data preparation and indexing.

Responsibilities (single-responsibility functions):
  1. chunk_document(doc_text, doc_name) → list of chunk dicts
  2. embed(text) → list[float]           (also used at query time)
  3. setup()                              (orchestrates chunking + indexing)

Collection name: trackflow_knowledge (from M7Context.md)
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
from openai import OpenAI

# Export embed so consumers can do: from data.process.rag import embed
__all__ = ["chunk_document", "embed", "setup", "EMBEDDING_DIM", "COLLECTION_NAME"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLLECTION_NAME = "trackflow_knowledge"
EMBEDDING_DIM = 1536  # text-embedding-3-small default

# ---------------------------------------------------------------------------
# Embedding model configuration
# ---------------------------------------------------------------------------

EMBEDDING_MODEL = os.getenv(
    "RAG_EMBEDDING_MODEL",
    "text-embedding-3-small",  # 4Geeks-provided embeddings model
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-placeholder")
OPENAI_BASE_URL = os.getenv(
    "OPENAI_BASE_URL",
    "https://api.openai.com/v1",
)


def embed(text: str) -> list[float]:
    """Generate a vector embedding for *text* using the dedicated embeddings
    model (NOT the generation model).

    This function is used both at index time (``setup`` chunks) and at query
    time (``retrieve``).  Consistency between both sides is guaranteed because
    they call the same ``embed()``.
    """
    if not text or not text.strip():
        return [0.0] * EMBEDDING_DIM

    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    resp = client.embeddings.create(input=text, model=EMBEDDING_MODEL)
    return resp.data[0].embedding


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def _get_qdrant_client():
    """Return a Qdrant client — local or cloud based on env."""
    from qdrant_client import QdrantClient

    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")
    location = os.getenv("QDRANT_LOCATION", ":memory:")

    if url:
        return QdrantClient(url=url, api_key=api_key or None)
    return QdrantClient(location=location)


def _ensure_collection(client) -> None:
    """Create the collection if it does not exist (idempotent)."""
    from qdrant_client.http.exceptions import UnexpectedResponse
    from qdrant_client.models import Distance, VectorParams

    collections = client.get_collections().collections
    exists = any(c.name == COLLECTION_NAME for c in collections)

    if not exists:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _normalize_text(text: str) -> str:
    """Normalize whitespace but preserve paragraph structure."""
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_document(doc_text: str, doc_name: str) -> list[dict[str, Any]]:
    """Split a Markdown document into semantic chunks, one per top-level
    heading (``#`` or ``##``).

    Strategy
    --------
    *Heading-level chunking* — each top-level Markdown heading starts a new
    chunk.  This preserves semantic units (sections, rules, conditions) so no
    sentence, table row, or policy clause is cut in half.

    Returns a list of payload dicts ready for Qdrant upsert.
    """
    text = _normalize_text(doc_text)

    # Source-document label for the payload
    source_map = {
        "sla-delivery": "sla-delivery",
        "returns-policy": "returns-policy",
        "carrier-coverage": "carrier-coverage",
        "storage-pricing": "storage-pricing",
    }
    source_document = "unknown"
    for key, value in source_map.items():
        if key in doc_name.lower():
            source_document = value
            break

    # Split on Markdown headings (## or #)
    heading_pattern = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)
    parts: list[str] = []
    headings: list[str] = []
    last_end = 0
    last_heading = "Introduction"

    for match in heading_pattern.finditer(text):
        # Save previous section
        section_text = text[last_end : match.start()].strip()
        if section_text:
            parts.append(section_text)
            headings.append(last_heading)

        last_heading = match.group(2).strip()
        last_end = match.start()

    # Last section after the final heading
    tail = text[last_end:].strip()
    if tail:
        parts.append(tail)
        headings.append(last_heading)

    # If no headings were found, treat the whole document as one chunk
    if not parts and text:
        parts = [text]
        headings = ["General"]

    chunks: list[dict[str, Any]] = []
    for i, (chunk_text, section) in enumerate(zip(parts, headings)):
        chunks.append({
            "source_document": source_document,
            "section": section,
            "company": "trackflow",
            "language": "en",
            "chunk_index": i,
            "text": chunk_text,
        })

    return chunks


# ---------------------------------------------------------------------------
# Setup — idempotent indexing
# ---------------------------------------------------------------------------

def _doc_id(doc_name: str, chunk_index: int) -> str:
    """Deterministic point ID for idempotent re-indexing.

    We use a CLEAR-AND-RELOAD strategy: ``setup`` recreates the collection
    each time it runs.  This is simpler and safer than trying to detect which
    points have changed, and is appropriate for a development / CI workflow
    where the full corpus fits easily in memory.
    """
    raw = f"{doc_name}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:48]


def setup() -> int:
    """Read source documents from ``docs/company-knowledge-base/``, parse them
    into semantic chunks, embed each chunk, and upsert into the Qdrant
    ``trackflow_knowledge`` collection.

    Returns the number of points indexed.
    """
    from qdrant_client.models import PointStruct

    docs_dir = Path(__file__).resolve().parents[2] / "docs" / "company-knowledge-base"

    if not docs_dir.is_dir():
        raise FileNotFoundError(
            f"Knowledge-base directory not found: {docs_dir}\n"
            "Make sure the source documents exist under docs/company-knowledge-base/"
        )

    # Collect all source documents
    documents: list[tuple[str, str]] = []  # (filename, content)
    for fpath in sorted(docs_dir.iterdir()):
        if fpath.suffix in (".md", ".txt", ".html", ".json") and fpath.is_file():
            documents.append((fpath.name, fpath.read_text(encoding="utf-8")))

    if not documents:
        raise FileNotFoundError(
            f"No source documents found in {docs_dir}. "
            "Add the TrackFlow knowledge base files (trackflow-sla-delivery.en.md, "
            "trackflow-returns-policy.en.md, trackflow-carrier-coverage.en.md, "
            "trackflow-storage-pricing.en.md)."
        )

    # Chunk all documents
    all_chunks: list[dict[str, Any]] = []
    for fname, content in documents:
        all_chunks.extend(chunk_document(content, fname))

    if not all_chunks:
        raise ValueError("No chunks were produced from the source documents.")

    # Connect to Qdrant and recreate collection (clear-and-reload strategy)
    client = _get_qdrant_client()

    from qdrant_client.http.exceptions import UnexpectedResponse

    try:
        client.delete_collection(COLLECTION_NAME)
    except (UnexpectedResponse, ValueError, Exception):
        pass  # Collection may not exist yet

    _ensure_collection(client)

    # Embed and upsert
    points: list[PointStruct] = []
    for chunk in all_chunks:
        vector = embed(chunk["text"])
        point_id = _doc_id(
            chunk["source_document"], chunk["chunk_index"]
        )

        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "company": chunk["company"],
                    "source_document": chunk["source_document"],
                    "section": chunk["section"],
                    "language": chunk["language"],
                    "chunk_index": chunk["chunk_index"],
                    "text": chunk["text"],
                },
            )
        )

    client.upsert(collection_name=COLLECTION_NAME, points=points)

    return len(points)


# ---------------------------------------------------------------------------
# Quick CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    count = setup()
    print(f"✅ Indexed {count} chunks into collection '{COLLECTION_NAME}'")
