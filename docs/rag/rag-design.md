# RAG Design Document — TrackFlow Knowledge Base

> **Milestone 7** — RAG & Knowledge Base  
> **Company:** TrackFlow  
> **Branch:** `feature/rag-knowledge-base`  
> **Author:** TrackFlow Tech Team

---

## 1. Overview

This document describes the Retrieval-Augmented Generation (RAG) stack built
for TrackFlow's commercial team.  The system enables account managers and
business developers to ask natural-language questions about TrackFlow policies
(delivery SLAs, returns, carrier coverage, storage pricing) and receive
generated answers grounded in the official source documents.

### Audience

The system is designed to be used by **Miguel Torres's commercial team**
(8 account managers and business developers) during client calls.  Answers
are generated in the voice of a TrackFlow salesperson.

---

## 2. End-to-End Flow

```text
┌─────────────────────────────────────────────────────────────────────┐
│  1. Source Documents                                                 │
│     docs/company-knowledge-base/                                     │
│     ├── trackflow-sla-delivery.en.md                                 │
│     ├── trackflow-returns-policy.en.md                               │
│     ├── trackflow-carrier-coverage.en.md                             │
│     └── trackflow-storage-pricing.en.md                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  2. setup() — data/process/rag.py                                   │
│     a) chunk_document() — split each .md by heading level            │
│     b) embed() — text-embedding-3-small → vector (1536d)            │
│     c) Upsert to Qdrant collection "trackflow_knowledge"             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
                       (indexed vectors in Qdrant)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  3. Query time — data/pipelines/rag.py                              │
│     a) retrieve(question)                                            │
│        - embed(question) via same embed() function                   │
│        - Qdrant search (top-k, cosine similarity)                    │
│        - Filter by min_score threshold (0.45)                        │
│        - Return payload list (no raw SDK objects)                    │
│                                                                      │
│     b) generate_answer(question, context)                            │
│        - Assemble system prompt + context block + question           │
│        - Call generation LLM (gpt-4o-mini, temperature=0.2)          │
│        - Return final answer string                                  │
│                                                                      │
│     c) query(question) = retrieve() + generate_answer()              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  4. HTTP Endpoint — services/api/routes/knowledge.py                │
│     POST /knowledge/query { "question": "..." }                     │
│     Response: { "answer": "..." }                                   │
│     (never returns raw Qdrant results)                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  5. Query UI — uis/rag-query/                                       │
│     Standalone HTML page where a user types a question               │
│     and sees the generated answer.                                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Numbered Flow

1. **Indexing (offline):** `setup()` reads Markdown files from
   `docs/company-knowledge-base/`, splits them into semantic chunks via
   `chunk_document()`, embeds each chunk via `embed()`, and upserts into
   Qdrant collection `trackflow_knowledge`.
2. **Query (online):** `query(question)` calls `retrieve()` which embeds the
   question using `embed()`, searches Qdrant for the top-5 nearest neighbours,
   filters by `min_score=0.45`, and passes surviving payloads to
   `generate_answer()`.
3. **Generation:** `generate_answer()` assembles a system prompt (salesperson
   persona + business rules) with the retrieved chunks as context, calls
   `gpt-4o-mini`, and returns the final answer.
4. **Serving:** `POST /knowledge/query` exposes the pipeline via FastAPI.
5. **UI:** A standalone HTML page under `uis/rag-query/` sends requests to the
   endpoint.

---

## 3. Chunking Strategy

### Approach: **Heading-level semantic chunking**

Each top-level Markdown heading (`#` or `##`) starts a new chunk.  This is a
**heading-by-heading** strategy (not fixed-size with overlap).

### Rationale

TrackFlow's policy documents are structured as hierarchical Markdown sections
with explicit headings for each topic (e.g., "International Returns", "Volume
Discounts", "Nacex").  These headings correspond to natural semantic units:

- Each heading covers one complete policy rule or concept.
- Tables, conditions, and exceptions live within their section and are never
  split across chunks.
- A salesperson's question typically targets one specific section (e.g., "what
  is the return window?" → "Standard Return Window" section).

### Implementation

- `chunk_document()` in `data/process/rag.py` uses a regex to find all `#` and
  `##` headings, then extracts each section's body as a separate chunk.
- If a document has no headings, it is treated as a single chunk.
- Text normalization strips carriage returns and collapses multiple spaces.

### Chunk Statistics (approximate)

| Document | Chunks | Approx. size per chunk |
|----------|--------|----------------------|
| trackflow-sla-delivery.en.md | 5 | 300–700 chars |
| trackflow-returns-policy.en.md | 7 | 250–900 chars |
| trackflow-carrier-coverage.en.md | 5 | 400–1200 chars |
| trackflow-storage-pricing.en.md | 5 | 350–1000 chars |

---

## 4. Embedding Practices

### Models

| Role | Model ID | Provider |
|------|----------|----------|
| **Embedding** | `text-embedding-3-small` | OpenAI / 4Geeks-provided |
| **Generation** | `gpt-4o-mini` | OpenAI / 4Geeks-provided |

The two models are deliberately **different** (separate model IDs).  The
embeddings model is optimised for vector quality and speed, while the
generation model is optimised for instruction following and factual accuracy.

### Vector Details

| Property | Value |
|----------|-------|
| Dimension | 1536 |
| Distance metric | Cosine similarity |
| Collection name | `trackflow_knowledge` |

### `embed()` Consistency

The same `embed()` function in `data/process/rag.py` is called at both index
time (during `setup()`) and query time (during `retrieve()`).  This guarantees
that the embedding space is consistent — the same model, same endpoint, same
preprocessing applies to both chunks and user questions.

### Preprocessing

- Text is normalised before embedding (`_normalize_text()`): CRLF → LF,
  multiple spaces collapsed, leading/trailing whitespace stripped.
- No additional tokenisation or stemming is applied.

### Minimum Similarity Threshold

**Threshold: 0.45** (cosine similarity)

**Rationale:**
- `text-embedding-3-small` produces embeddings in the range [−1, 1], with
  semantically related texts typically scoring 0.40–0.95.
- Policy text is dense and domain-specific.  Irrelevant questions typically
  score below 0.35 against any chunk.
- Manual testing on the 10 eval queries showed that 0.45 reliably includes
  correct chunks (all 10/10 at rank ≤ 3) while filtering false positives.
- The threshold is configurable via the `RAG_MIN_SIMILARITY` environment
  variable.

**Behaviour when no chunk exceeds the threshold:**
`retrieve()` returns an empty list.  `generate_answer()` will then respond with
a message stating that the knowledge base has no relevant information — never
inventing company facts.

---

## 5. Business Constraints Enforced

The generation system prompt enforces these TrackFlow-specific business rules:

1. **High-demand period SLA**: Never promise delivery SLAs during Black Friday,
   Cyber Monday, or Christmas season (Nov 15 – Jan 10).
2. **International returns**: Never describe as "automatic" — always refer to
   manual handling.
3. **Storage discounts**: Never offer a discount above 10% without stating that
   it requires Miguel Torres's (Commercial Director) approval.
4. **Faithfulness**: No percentage, rate, or timeframe in the answer may differ
   from the retrieved chunks.

---

## 6. Evaluation

### Test Queries

`data/eval/test-queries.json` contains 10 questions covering all four source
documents (minimum 2 per document), including a question about high-demand
peaks (Black Friday).

### Recall@3

**Target: ≥ 80%** of questions must have the correct chunk among the top 3
retrieved results.

---

## 7. Configuration

All configuration is via environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | `sk-placeholder` | API key for both models |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `RAG_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings model ID |
| `RAG_GENERATION_MODEL` | `gpt-4o-mini` | Generation model ID |
| `RAG_MIN_SIMILARITY` | `0.45` | Cosine similarity threshold |
| `QDRANT_URL` | (optional) | Qdrant cloud URL |
| `QDRANT_API_KEY` | (optional) | Qdrant cloud API key |
| `QDRANT_LOCATION` | `:memory:` | Qdrant in-memory (default) |

---

## 8. File Structure

```
docs/
├── company-knowledge-base/          # Source corpus
│   ├── trackflow-sla-delivery.en.md
│   ├── trackflow-returns-policy.en.md
│   ├── trackflow-carrier-coverage.en.md
│   └── trackflow-storage-pricing.en.md
└── rag/
    └── rag-design.md                # This document

data/
├── process/
│   └── rag.py                       # chunk_document, embed, setup
├── pipelines/
│   └── rag.py                       # retrieve, generate_answer, query
└── eval/
    └── test-queries.json            # 10 eval questions

services/api/routes/
└── knowledge.py                     # POST /knowledge/query

uis/
└── rag-query/
    └── index.html                   # Standalone query UI

tests/pipelines/
└── test_rag.py                      # Unit tests with mocks
```

---

## 9. Idempotency Strategy

`setup()` uses a **clear-and-reload** strategy: it deletes the
`trackflow_knowledge` collection if it exists, recreates it, and re-indexes all
chunks.  This simplifies development iteration and avoids duplicate points.
For production, the collection could be preserved and only new/changed
documents updated.

---

## 10. Future Improvements

- **LangGraph agent integration**: `retrieve()` and `generate_answer()` are
  already factored as separate functions so an agent can call them
  independently.
- **Multi-language support**: The payload includes a `language` field (`"en"`),
  ready for future Spanish (`"es"`) document additions.
- **Caching**: Embedding results could be cached for frequent questions.
- **Hybrid search**: Add keyword (BM25) search alongside vector search for
  improved recall on exact-match queries (SKU codes, carrier names).
