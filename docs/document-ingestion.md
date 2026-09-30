# Document Ingestion

This document explains what happens from the moment a file is uploaded until it
is searchable, and — just as important — what NEXORA does **not** support.

## Supported formats (and only these)

NEXORA extracts text from exactly two formats:

- **PDF** (`.pdf`, `application/pdf`) — via `pymupdf`. Text is extracted
  **per page**, and page numbers start at 1.
- **DOCX** (`.docx`, the Office Open XML word-processing MIME type) — via
  `python-docx`. Both **paragraphs and tables** are read; table cells are joined
  with `" | "`. A DOCX is treated as a single logical page (page 1).

Anything else raises `DocumentExtractionError("Unsupported document format")`.

### Explicitly NOT supported

- **No OCR.** Scanned PDFs or image-only documents yield no text.
- **No image understanding.** Images inside documents are ignored.
- **No table extraction from PDFs.** Only DOCX tables are parsed; PDF tables are
  read as plain text flow, not as structured rows/columns.
- **No plain `.txt`, `.md`, `.xlsx`, `.pptx`, `.csv`, or `.html`** ingestion.

Do not describe NEXORA as supporting OCR, images, or PDF tables — the code does
not.

## Upload validation

`POST /api/v1/organizations/{id}/documents/upload` (multipart) validates before
accepting a file (`_validate_upload` / `_read_upload` in
`document_service.py`):

1. **Filename** must be non-empty.
2. **Content** must be non-empty.
3. **Size** must be ≤ `MAX_UPLOAD_SIZE_BYTES` (default 10 MiB). The body is read
   in 1 MB chunks and rejected as soon as it exceeds the limit, so a huge upload
   is not buffered into memory.
4. **Content type** must be in the allowlist (`application/pdf` or the DOCX MIME
   type).
5. **Magic bytes** must match the declared type: a PDF must start with `%PDF-`, a
   DOCX must start with `PK` (the ZIP signature). This stops a file with a
   spoofed extension/MIME type.

Validation failures return **400** (`InvalidDocumentUploadError`).

There is also a metadata-only `POST /organizations/{id}/documents` that creates
a `documents` row without a file (status `pending`).

## Storage

Uploaded bytes are written under `STORAGE_PATH` (default `storage/`) using a
storage key. The local storage backend confines every path **within** the base
directory (`_resolve_within_base` + `is_relative_to`), so a crafted filename
cannot traverse outside (`../../etc/...` is blocked).

## Processing pipeline (background)

Processing runs in a **FastAPI BackgroundTask** (`process_document_background`),
so the upload request returns immediately with status `pending`. The worker
(`document_processing_service.py`) then:

1. Sets status → **`processing`**.
2. **Extracts** text (page-aware) via `extract_document`.
3. **Chunks** the text via `split_document`.
4. **Replaces** the document's chunks in Postgres (old chunks removed).
5. Updates extraction stats (`page_count`, `word_count`, `character_count`) and
   commits.
6. **Invalidates** the organization's cached BM25 index.
7. **Indexes** chunks into Qdrant (`index_document_chunks`).
8. Sets status → **`ready`**.

On any exception the transaction is rolled back, the document is re-fetched and
set to **`failed`** with a short `failure_reason`, and the error is re-raised
for logging.

### Failure reasons

`failure_reason` is deliberately generic (it is returned by the API and must not
leak internals):

- `EmptyDocumentTextError` → "Document contains no extractable text"
- `DocumentExtractionError` → "Document text extraction failed"
- anything else → "Document processing failed"

## Chunking

`document_chunking.py` uses `RecursiveCharacterTextSplitter` with:

- **chunk size 3000** characters,
- **overlap 400** characters,
- separators `["\n\n", "\n", ". ", " ", ""]` (paragraph → line → sentence →
  word → character).

Each chunk keeps **page provenance**: `split_document` maps character offsets
back to source pages and returns a `ChunkSpan(text, page_start, page_end)`. For
DOCX (single logical page) both are 1. Chunks that cannot be mapped to a page
are logged as a warning.

Page provenance is what lets citations show a page range in query responses.

## Embedding and indexing

`index_document_chunks` (`document_indexing_service.py`):

1. Loads the document (organization-scoped) and its chunks.
2. **Deletes** the document's existing Qdrant vectors first (idempotent reindex).
3. Embeds chunks in batches of `EMBEDDING_BATCH_SIZE` (32) with BGE-M3.
4. Validates that the embedding count matches the chunk count and that every
   vector has `EMBEDDING_DIMENSION` (1024) dimensions.
5. Upserts points in batches of `QDRANT_UPSERT_BATCH_SIZE` (32). Each point's id
   is the Postgres chunk id, with payload `{organization_id, document_id,
   chunk_id, chunk_index}`.

If a document has no chunks, indexing returns 0 without touching Qdrant.

## Versioning and re-indexing

Replacing a document's content (`/versions`, admin/owner) purges the old vectors
and chunks, bumps `version`, and reprocesses — so the vector index always
reflects the current content.

## BM25 index

The lexical (BM25) index is built **lazily per organization** from that
organization's chunk text and cached in memory (`bm25_service.py`, guarded by an
`RLock`). It is invalidated whenever chunks change (upload, version replace,
delete). The tokenizer lowercases text and splits on `\w+` (word characters),
and chunks with zero query-term overlap are filtered out of results.
