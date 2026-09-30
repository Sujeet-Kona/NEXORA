# RAG Pipeline

RAG (Retrieval-Augmented Generation) is the end-to-end path from a question to a
grounded, cited answer. This document explains the generation half; the
retrieval half is in [retrieval.md](retrieval.md).

## The flow

```
question (+ optional document_ids)
        │
        ▼
 hybrid retrieval  → 0..N chunks (default top 2, after relevance threshold)
        │
        ├── 0 chunks ──► canned refusal, NO LLM call
        │
        └── ≥1 chunk ──► number the chunks [1]..[N]
                          build grounded system prompt
                          call the LLM (Ollama qwen3:8b)
                          strip invalid citation markers
                          return answer + sources
```

## Grounded generation

The retrieved chunks are numbered `[1] … [N]` and placed into a **grounded
system prompt** that instructs the model to:

- answer **only** from the provided context,
- cite the supporting passage(s) inline as `[n]`,
- use **no outside knowledge**,
- explicitly say so if the context is insufficient.

This prompt is what makes the answers "grounded": the model is told to refuse
rather than guess.

## Two refusal mechanisms

NEXORA declines to answer unsupported questions in two independent ways:

1. **Deterministic (no LLM).** If retrieval returns **zero** chunks that clear
   the relevance threshold, the service returns the canned
   `NO_CONTEXT_ANSWER`:
   > "The available documents do not contain enough information to answer this
   > question."

   The LLM is **not called at all**. This is fast, cheap, and cannot hallucinate.

2. **Model judgement.** If some chunks are retrieved but they do not actually
   answer the question, the grounded prompt tells the model to say so. The model
   then produces a refusal in its own words.

## Citation validation

The model is asked to emit `[n]` markers, but it can emit markers that point at
nothing. `generation_service.py` runs `_strip_invalid_citations`: a regex
(`( ?)\[(\d{1,2})\]`) finds every marker and **removes any whose number is
outside `1..N`** (the number of real sources). So a `[5]` in a 2-source answer
is stripped before the response is returned. Valid markers are kept and map to
the `citation_index` of the returned sources.

## Response shape

`POST /api/v1/organizations/{id}/query` returns:

```json
{
  "answer": "Employees receive 20 days of annual leave per year [1].",
  "sources": [
    {
      "citation_index": 1,
      "chunk_id": 42,
      "document_id": 7,
      "document_name": "leave_policy.docx",
      "chunk_index": 0,
      "score": 0.87,
      "page_start": 1,
      "page_end": 1
    }
  ]
}
```

- `citation_index` is 1-based and matches the `[n]` markers in the answer.
- `page_start` / `page_end` give page-level provenance (1 for DOCX).
- `score` is the reranker relevance.

## Streaming (SSE)

`POST /api/v1/organizations/{id}/query/stream` returns
`text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`.
Retrieval still happens **eagerly** (so retrieval errors surface as normal HTTP
exceptions before streaming starts), then events are emitted:

- `token` — incremental answer text as the LLM produces it.
- `done` — terminal event with the full `answer`, `sources`, and
  `timing` (`ttft_ms`, `total_ms`).
- `error` — terminal event if generation fails mid-stream.

`ttft_ms` is **time to first token** (how long until the first word appears);
`total_ms` is the whole request. The canned-refusal path emits a `done` event
immediately with near-zero generation time (no LLM call).

## LLM provider abstraction

`backend/services/llm/provider.py` builds the client from `LLM_PROVIDER`:

- **`ollama`** (default) → `OllamaLLMClient`. POSTs to
  `{base}/api/chat` with `model`, `messages`, `stream`, `think`, and
  `options.num_predict`; keeps the model warm with `keep_alive="5m"`.
- **`openai`** → `OpenAICompatibleLLMClient` (uses the `openai` SDK, supports a
  custom `OPENAI_BASE_URL` gateway). The API key is never logged.
- anything else → `LLMConfigurationError`.

Both clients implement the same `LLMClient` protocol (`generate`, `stream`) and
map every provider failure (timeout, connection, 404, HTTP error, malformed
JSON) to a single `LLMGenerationError`.

## Error contract

- `LLMGenerationError` → **503** with a static message "LLM provider request
  failed" (the underlying reason is logged, not returned).
- `LLMConfigurationError` → **500** with a static message "LLM provider is not
  configured".
- An empty answer from the LLM is treated as a generation error (503), not a
  silent blank response.

Callers never see provider internals, stack traces, or secrets — only a stable,
safe message plus the `X-Request-ID` header for support.

## Why no LangChain/LangGraph

The RAG flow is plain Python in `rag_service.py` / `generation_service.py`. An
earlier LangGraph implementation was removed; the current orchestration is a
direct function call sequence, which is easier to test, debug, and reason about.
Only `langchain-text-splitters` (chunking) and `langchain-huggingface`
(embeddings) remain as focused utilities.
