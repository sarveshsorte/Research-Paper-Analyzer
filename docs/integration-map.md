# Integration map: backend ↔ teammates' pipelines

Phase 0 output. It records how the Document Pipeline and Query Pipeline on `Main2` work
today, where the backend has to plug in, and what is missing. It contains no feature code.

- Branch: `Main2` at `30fb810`.
- §4 means the API contract in [`FRONTEND_BUILD_PROMPT.md`](FRONTEND_BUILD_PROMPT.md#4-api-contract-backend-fastapi-base-apiv1),
  which the React app already uses.
- §5 (the adapter interface) was not included in the build prompt I received. The adapter
  shapes in [Proposed layout](#7-proposed-folder-layout-and-python-setup) are inferred from
  Phases 3–4. Please confirm or replace them.

## 1. How the pipelines run today

There is no CLI, notebook or script that runs either pipeline end to end. Both are libraries:

| Pipeline                                 | How it is run                                                                                                                                                             | Owner's instructions                                                                  |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Document Pipeline (`document_pipeline/`) | Python calls (`ingest_pdf`, `ingest_and_embed_pdf`, `index_prepared_paper`, `index_pdf`), plus one integration test `tests/document_pipeline/test_end_to_end_indexing.py` | [`document_pipeline/README.md`](../document_pipeline/README.md)                       |
| Query Pipeline (`query_pipeline/`)       | `QueryOrchestrator.run()`, exposed by the backend route `POST /api/v1/workspaces/{workspace_id}/query`. `pytest -q` covers it with fake providers.                        | [`query_pipeline/README.md`](../query_pipeline/README.md), `query_pipeline/docs/*.md` |

- **The current API doesn't use them yet.** The backend's `/query`, `/compare`, `/contradiction`
  and `/check` (`backend/app/api/routes/workflows.py`) answer with a word-matching search over
  SQLite. Uploads call only `ingest_pdf` (extraction and chunking), not embedding or indexing.
- **Legacy duplicates, unused:**
  - `document pipeline/`, with a space in its name, is an older copy of `document_pipeline/`.
    It can't be imported because of the space.
  - `researchlens-query-service/tests/` holds 2 stale copies of query-pipeline tests.
  - I left both untouched; the owners may want to delete them.

## 2. Entry points

The backend should call these and nothing deeper.

| Need                                     | Function (file:line)                                                                                                                                                                                                                                                                                                                                                                                                                    | Inputs → output                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ingest one PDF: extract + chunk only** | `ingest_pdf` — [`document_pipeline/ingestion/service.py:38`](../document_pipeline/ingestion/service.py#L38)                                                                                                                                                                                                                                                                                                                             | `source: str \| Path \| bytes \| BinaryIO`, `workspace_id: str`, `paper_id: str`, `paper_title: str \| None`, `ocr_fallback=True`, `ocr_dpi=300`, `max_chunk_tokens=500`, `overlap_tokens=50` → `IngestedPaper` (`:27`): `paper_title`, `metadata`, `pages: tuple[ExtractedPage]`, `sections`, `chunks: tuple[IngestionChunk]`. Sync and CPU-bound. |
| Ingest + embed (no index writes)         | `ingest_and_embed_pdf` — [`document_pipeline/pipeline.py:67`](../document_pipeline/pipeline.py#L67)                                                                                                                                                                                                                                                                                                                                     | Same as above plus `embedding_provider` (anything with `async embed(text) -> list[float]`), `expected_dimension=2048`, `max_embedding_concurrency=4` → `PreparedPaper(paper, embedded_chunks)`. Async.                                                                                                                                              |
| Write to Qdrant + BM25                   | `index_prepared_paper` — [`document_pipeline/pipeline.py:34`](../document_pipeline/pipeline.py#L34)                                                                                                                                                                                                                                                                                                                                     | `PreparedPaper`, `vector_indexer: QdrantVectorIndexer`, `bm25_indexer: BM25Indexer` → `IndexingResult(workspace_id, paper_id, qdrant_points, bm25_documents)`. Idempotent per chunk id. Async.                                                                                                                                                      |
| All three, from settings                 | `index_pdf` — [`document_pipeline/service.py:14`](../document_pipeline/service.py#L14)                                                                                                                                                                                                                                                                                                                                                  | `source`, `workspace_id`, `paper_id`, `paper_title?`, `ocr_dpi`, `settings?` → `IndexingResult`. Refuses to run while `USE_FAKE_PROVIDERS` is true, which is the default outside `APP_ENV=production`.                                                                                                                                              |
| **Delete a paper**                       | **None.** Neither indexer can delete by paper (see [G5](#g5)).                                                                                                                                                                                                                                                                                                                                                                          | —                                                                                                                                                                                                                                                                                                                                                   |
| **Answer a question**                    | `QueryOrchestrator.run` — [`query_pipeline/app/pipeline/orchestrator.py:60`](../query_pipeline/app/pipeline/orchestrator.py#L60). Built at `:35` from `settings`, `embedding_provider`, `dense_retriever`, `generator`, `paper_repository`, `chunk_repository`, plus optional `sparse_retriever`, `reranker` and `answer_repository`.                                                                                                   | `workspace_id: str`, `QueryRequest` ([`schemas/query.py:9`](../query_pipeline/app/schemas/query.py#L9): `question`, `paper_ids[1..20]`, `filters`) → `QueryResponse` (`:49`): `query_id`, `answer`, `claims: ClaimResponse[]`, `citations: Citation[]`, `uncertainties`, `pipeline_status`. Async.                                                  |
| **Compare**                              | **None.** `classify_question` ([`classification.py:17`](../query_pipeline/app/pipeline/classification.py#L17)) only labels "compare" questions (see [G6](#g6)).                                                                                                                                                                                                                                                                         | —                                                                                                                                                                                                                                                                                                                                                   |
| **Contradiction**                        | **None.** Only labelled, at `classification.py:13`.                                                                                                                                                                                                                                                                                                                                                                                     | —                                                                                                                                                                                                                                                                                                                                                   |
| **Claim analysis (/check)**              | **None.**                                                                                                                                                                                                                                                                                                                                                                                                                               | —                                                                                                                                                                                                                                                                                                                                                   |
| **Citation validation**                  | `map_claim` — [`citations/mapper.py:8`](../query_pipeline/app/citations/mapper.py#L8), which runs `validate_claim` ([`validator.py:6`](../query_pipeline/app/citations/validator.py#L6): cited source ids ⊆ supplied ids) and `check_claim_support` ([`support_checker.py:13`](../query_pipeline/app/citations/support_checker.py#L13): numbers must match, and any shared word counts as support). Both run inside `orchestrator.run`. | `GeneratedClaim`, `list[EvidenceSource]` → `ClaimResponse(text, source_ids, citation_text, validation_status: valid\|invalid\|unsupported\|needs_review)`. Nothing checks that a quote's text is really in the chunk; that is the backend's citation guard (Phase 4).                                                                               |

Examples, taken from the Phase 0 run in [§9](#9-pipeline-run-on-a-sample-pdf):

```python
paper = ingest_pdf(pdf_path, workspace_id="workspace_001", paper_id="paper_001")
# 26 pages, 26 chunks; title 'Quantized Adapters for Open Models'
paper.chunks[0]
# IngestionChunk(chunk_id='chunk_ff9c96cbdeabdb0ddf30e11e39d188d3', workspace_id='workspace_001',
#   paper_id='paper_001', paper_title='Quantized Adapters for Open Models',
#   text='1 INTRODUCTION   …', page_start=1, page_end=1, section='Introduction',
#   content_type='text', chunk_index=0, content_hash='…sha256 of text…')

await index_prepared_paper(prepared, vector_indexer=..., bm25_indexer=...)
# IndexingResult(workspace_id='workspace_001', paper_id='paper_001', qdrant_points=26, bm25_documents=26)

await orchestrator.run("workspace_001", QueryRequest(question="What were the main results?",
                                                     paper_ids=["paper_001"]))
# QueryResponse(query_id='…uuid…', answer='…', pipeline_status='completed',
#   claims=[ClaimResponse(text='…', source_ids=['S1'],
#           citation_text='[Quantized Adapters for Open Models, p. 8]', validation_status='valid')],
#   citations=[Citation(source_id='S1', chunk_id='chunk_…', paper_id='paper_001', page_start=8,
#           page_end=8, section='Results', snippet='<whole chunk text>', validation_status='valid'), …])
```

`pipeline_status` can be `completed`, `insufficient_evidence`, `no_ready_papers`,
`paper_not_ready`, `invalid_request` or `generation_failed`. Everything except `completed`
comes back as a normal response, not an exception.

## 3. Where data lives

| What                                     | Where                                                                                                               | Details                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vectors                                  | **Qdrant**                                                                                                          | `QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)`. Collection `QDRANT_COLLECTION` (default `paper_chunks`): one unnamed vector of `EMBEDDING_DIMENSION` (default 2048), cosine. Created on first upsert, with payload indexes on `workspace_id`, `paper_id`, `section`, `content_type`, `page_start` and `page_end` ([`vector_indexer.py:15`](../document_pipeline/indexing/vector_indexer.py#L15)). Point id = `uuid5(NAMESPACE_URL, chunk_id)`; the payload holds every `IngestionChunk` field, text included. There is no Qdrant service in `docker-compose.yml` yet. |
| BM25                                     | **SQLite FTS5** file at `BM25_INDEX_PATH` (default `storage/bm25/index.sqlite3`, relative to the working directory) | Virtual table `chunks_fts` with the same fields as the payload. `BM25Indexer.search` ([`bm25_indexer.py:50`](../document_pipeline/indexing/bm25_indexer.py#L50)) always filters by `workspace_id` and `paper_id IN (…)`.                                                                                                                                                                                                                                                                                                                                                      |
| Chunk id                                 | Deterministic                                                                                                       | `"chunk_" + sha256(workspace_id ␀ paper_id ␀ page ␀ section ␀ chunk_index ␀ content_hash)[:32]` ([`page_aware_chunker.py:82`](../document_pipeline/chunking/page_aware_chunker.py#L82)). The same file under the same ids gives the same chunk ids. The id depends on `workspace_id` (see [G18](#g18)).                                                                                                                                                                                                                                                                       |
| Chunk text, page and section by chunk id | **Stored, but no lookup function**                                                                                  | Qdrant (payload) and BM25 (row) both hold the exact text, `page_start`/`page_end` and `section`, but neither exposes "get by chunk_id". Recommendation: the backend saves `IngestedPaper.chunks` in its own DB when it ingests, as it already does in its `chunks` table, and serves `GET /chunks/{id}` and the citation guard from there. Pages are 1-based and inclusive; one chunk never spans pages.                                                                                                                                                                      |
| Page text                                | Not persisted                                                                                                       | `IngestedPaper.pages` exists only in memory.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| PDF files                                | Backend, not the pipeline                                                                                           | Today they are a BLOB in the backend's SQLite (`documents.file_bytes`). Phase 3 moves them to `UPLOAD_DIR/{document_id}.pdf`.                                                                                                                                                                                                                                                                                                                                                                                                                                                 |

## 4. Models and keys

All model calls are remote HTTP. **No model runs locally, so there are no model weights to load
or cache.**

| Role                               | Code                                                                                                                                                                                                                                                                 | Model id                                                                                                 | Env vars (read by `backend/app/config.py:8`)                                                                                                                          |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Embeddings (documents and queries) | `OpenAICompatibleEmbeddingProvider` — [`embedding_provider.py:9`](../query_pipeline/app/providers/embedding_provider.py#L9). `POST {base}/embeddings`, one text per request, new `httpx` client per call, 30 s timeout.                                              | `.env.example` suggests `nvidia/nemotron-3-embed-1b` at `https://integrate.api.nvidia.com/v1`, 2048 dims | `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`                                                                                   |
| Reranker                           | Only `ScoreBasedReranker` ([`reranker_provider.py:13`](../query_pipeline/app/providers/reranker_provider.py#L13)), which counts shared words. **No real reranker client exists**, and nothing reads the settings.                                                    | —                                                                                                        | `RERANKER_BASE_URL`, `RERANKER_API_KEY`, `RERANKER_MODEL` (unused)                                                                                                    |
| Answer generation (Nemotron)       | `OpenAICompatibleGenerationProvider` — [`nemotron_provider.py:15`](../query_pipeline/app/providers/nemotron_provider.py#L15). This is the **Token Factory client**: `POST {base}/chat/completions`, `temperature 0.1`, `response_format: json_object`, 60 s timeout. | **Not set anywhere** (`NEBIUS_MODEL` is empty)                                                           | `NEBIUS_BASE_URL` (default `https://api.tokenfactory.us-central1.nebius.com/v1/`), `NEBIUS_API_KEY`, `NEBIUS_MODEL`                                                   |
| Guardrail model                    | Not implemented                                                                                                                                                                                                                                                      | —                                                                                                        | `GUARDRAIL_*` in `query_pipeline/.env.example`; not in `Settings`, ignored                                                                                            |
| Retrieval knobs                    | `orchestrator.run`                                                                                                                                                                                                                                                   | —                                                                                                        | `TOP_K_DENSE` 25, `TOP_K_SPARSE` 25, `TOP_K_RERANKED` 8, `MAX_CONTEXT_TOKENS` 6000, `MIN_RELEVANCE_SCORE` 0.65, `MAX_QUESTION_LENGTH` 4000, `MAX_PAPERS_PER_QUERY` 20 |
| Fake-provider switch               | `get_orchestrator` ([`backend/app/dependencies.py:16`](../backend/app/dependencies.py#L16)), `index_pdf`                                                                                                                                                             | —                                                                                                        | `USE_FAKE_PROVIDERS` (defaults to `APP_ENV != "production"`; fakes are refused in production)                                                                         |

`Settings` reads `.env` from the working directory and then `query_pipeline/.env`
(`config.py:50`). Neither file exists locally, so **no real model call can be made yet**.
Before Phase 3/4 can run for real, I need: `EMBEDDING_API_KEY` (and to confirm the embedding
endpoint and model), `NEBIUS_API_KEY`, the Nemotron model id for `NEBIUS_MODEL`, and the
Firebase service account.

## 5. Gaps vs §4/§5, with the smallest fix

"**Backend-only**" means the fix lives in `backend/` and needs nothing from you.
"**Pipeline change**" means editing teammates' code, which needs your OK and its own commit.
The pipeline's providers and repositories are Python protocols (interfaces), so most fixes can
be backend classes passed into `QueryOrchestrator` without touching their code.

<a id="g1"></a>**G1 — Real dense retrieval crashes.**

- `QdrantDenseRetriever` calls `client.search(...)` ([`qdrant_provider.py:45`](../query_pipeline/app/providers/qdrant_provider.py#L45)).
- `qdrant-client` 1.19.1, which `qdrant-client>=1.9` installs today, has no `search()`.
- Reproduced: `AttributeError: 'QdrantClient' object has no attribute 'search'`.
- _Fix (backend-only):_ a backend `DenseRetriever` that uses `query_points()` and returns the
  same `RetrievalCandidate`s. _Alternative (pipeline change, 1 call):_ switch line 45 to
  `query_points(...).points`.

<a id="g2"></a>**G2 — Even with `search()` fixed, every hit would fail validation.**

- The same adapter passes `chunk_index=` ([`qdrant_provider.py:66`](../query_pipeline/app/providers/qdrant_provider.py#L66)),
  but `RetrievalCandidate` forbids extra fields and has no `chunk_index`.
- Reproduced: `ValidationError … chunk_index`.
- _Fix:_ the same backend retriever as G1. _Alternative (pipeline change, 1 line):_ delete line 66.

<a id="g3"></a>**G3 — The BM25 index written by ingestion is never queried.**

- The only sparse retriever is `InMemoryBM25Retriever` ([`bm25_provider.py:19`](../query_pipeline/app/providers/bm25_provider.py#L19)).
- _Fix (backend-only):_ a `SparseRetriever` that wraps `BM25Indexer.search` and maps hits to
  `RetrievalCandidate`.

<a id="g4"></a>**G4 — With BM25 on and no reranker, every answer is "insufficient evidence".**

- The threshold ([`thresholds.py:4`](../query_pipeline/app/pipeline/thresholds.py#L4)) compares
  the first available score (reranker score, then fusion score, then dense score, then BM25
  score) with `MIN_RELEVANCE_SCORE=0.65`.
- After merging dense and BM25 results, the fusion score is at most ≈0.03 (rank fusion with k=60).
- Reproduced: dense only → `completed`; dense + sparse → `insufficient_evidence`.
- _Fix (backend-only):_ always pass a reranker. Their `ScoreBasedReranker` works now
  (scores ≥ 1 when terms match); swap in a real reranker later.

<a id="g5"></a>**G5 — No delete.** Neither `QdrantVectorIndexer` nor `BM25Indexer` can remove a
paper's chunks.

- _Fix (pipeline change, ~20 lines, recommended):_ `delete_paper(workspace_id, paper_id)` on
  both indexers: a Qdrant delete filtered on `paper_id`, and
  `DELETE FROM chunks_fts WHERE workspace_id=? AND paper_id=?`.
- _Backend-only alternative:_ the adapter runs those two deletes itself. That ties the backend
  to their internal table name `chunks_fts`.

<a id="g6"></a>**G6 — No compare, contradiction or claim-analysis functions.**

- The orchestrator answers one question.
- _Fix (backend-only):_ `QueryPipelineAdapter` builds these from their parts: retrieval through
  the same retrievers (filtered per paper or topic), source ids from `assign_source_ids`, and
  one Nemotron call per task with a backend prompt that asks for JSON:
  - compare: `{attribute → {document_id → value, source_id}}`;
  - contradiction: pairs of source ids with a status and explanation.
- Source ids map back to chunk, page and section from the retrieved metadata. The model can't
  invent pages, the same rule the pipeline uses. The citation guard runs on the result.
- `/check` (claim analysis) is Phase 6 and reuses this.

<a id="g7"></a>**G7 — No progress hooks.** `orchestrator.run` is one opaque call.

- _Fix (backend-only):_ the adapter wraps the providers it passes in. Embedding and retriever
  calls emit `retrieving` (with counts), the reranker emits `reranking`, the generator emits
  `reasoning`, and the citation guard emits `validating`. These are the §4 step types.
- _Optional pipeline change:_ an `on_step` callback parameter on `run`.
- For uploads, call `ingest_pdf`, `embed_chunks` and `index_prepared_paper` separately (not
  `index_pdf`), so `progress` can move per stage and per embedded chunk.

<a id="g8"></a>**G8 — The real wiring can never find a ready paper.**

- `get_orchestrator` ([`dependencies.py:16`](../backend/app/dependencies.py#L16)) passes empty
  `InMemoryPaperRepository` and `InMemoryChunkRepository`, so `validate_query` always returns
  `no_ready_papers`.
- An empty `InMemoryWorkspaceRepository` also turns any `user_id` into a 403.
- _Fix (backend-only):_ `PaperRepository` and `ChunkRepository` backed by the backend DB
  (status `ready`, chunk count > 0). Don't pass `user_id`; the backend checks ownership itself.

<a id="g9"></a>**G9 — The output doesn't match §4's `QueryResult`.**

| Pipeline returns                                                                                     | §4 expects                                                                                  |
| ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `ClaimResponse(text, source_ids, citation_text, validation_status)`, with no confidence and no quote | `Claim{claim, status, confidence, evidence[{chunk_id, document_id, page, section, quote}]}` |
| `Citation.snippet` = the whole chunk (up to ~500 words)                                              | a short `quote`                                                                             |
| `[Title, p. 7]` labels                                                                               | `[n]` markers                                                                               |

- _Fix (backend-only mapping):_
  - `valid` → `SUPPORTED`; anything else is dropped (the pipeline already fails the whole
    answer if any claim is invalid).
  - `quote` = the sentence(s) in the cited chunk that best match the claim. It is always a
    substring of the chunk, so the guard can check it.
  - `document_id` = `paper_id`.
- `GeneratedClaim.confidence` is dropped by `map_claim`. _Pipeline change, 1 field:_ carry
  `confidence` on `ClaimResponse`. Until then, use a fixed value.

<a id="g10"></a>**G10 — The Nemotron prompt never describes the JSON it must return.**

- The prompt is in [`nemotron_provider.py:35`](../query_pipeline/app/providers/nemotron_provider.py#L35);
  the unused one is `generation/prompts.py`.
- `parse_generated_answer` expects `{answer, claims[{text, source_ids, …}], uncertainties}`, so a
  real model will often produce something unparseable → `generation_failed`.
- _Fix (backend-only):_ a backend `GenerationProvider` with the schema in the prompt, which
  also tells the model that evidence is data, not instructions (PDF text is untrusted).
- _Pipeline alternative:_ add the schema to their prompt.
- Their `injection_guard` and `scope_guard` exist but are never called.

<a id="g11"></a>**G11 — The pipelines import backend modules.**

- `document_pipeline/service.py:5` and `orchestrator.py:6` import `backend.app.config.Settings`.
- `orchestrator.py:12` imports `backend.app.observability.logging.get_logger`.
- _Fix (backend-only):_ Phase 1 keeps both module paths and every `Settings` field the
  pipelines read. Re-export them if files move.

<a id="g12"></a>**G12 — Some code is synchronous.**

- `ingest_pdf` is sync and CPU-bound (≈1 s for 26 pages).
- `BM25Indexer` is sync; the pipeline already runs it in a thread inside `index_prepared_paper`.
- Qdrant calls run in threads.
- _Fix (backend-only):_ run `ingest_pdf` in a thread (already done) and keep one `QdrantClient`
  for the app's lifetime.

<a id="g13"></a>**G13 — Paths that depend on where the app starts.**

- `BM25_INDEX_PATH` and `STORAGE_PATH` are relative to the working directory, and `Settings`
  also reads `query_pipeline/.env`.
- The backend passes `workspace_id="default"` when it ingests.
- _Fix (backend-only):_ absolute paths in Docker (`/app/storage/...`) and one workspace id
  constant (G18).

<a id="g14"></a>**G14 — `index_pdf` is unusable in development.**

- It refuses whenever `USE_FAKE_PROVIDERS` is true, which is the default outside production.
- _Fix (backend-only):_ the adapter uses the lower-level functions (also needed for G7), and
  `USE_FAKE_PROVIDERS=false` whenever real keys are set.

<a id="g15"></a>**G15 — Scanned PDFs need Tesseract.**

- OCR (`ocr_fallback=True`) raises `OCRProcessingError` without the `tesseract` binary. It isn't
  installed here or in `docker/backend.Dockerfile`.
- _Fix (backend-only):_ add `tesseract-ocr` to the backend image. Without it, fail the document
  with "This PDF needs OCR".

<a id="g16"></a>**G16 — Health and error shapes.**

- `GET /health` returns `{status}` only; §4 wants `{status, version, mock_ai}`.
- Errors come back as FastAPI's `{detail}`; §4 wants `{error: {code, message}}`.
- _Fix:_ Phase 1. 401 `UNAUTHENTICATED` is a new code on top of §4's list.

<a id="g17"></a>**G17 — The doc-id filter: no gap.** Qdrant (`MatchAny` on `paper_id`) and BM25
(`paper_id IN`) both require the selected paper ids, plus the workspace.

<a id="g18"></a>**G18 — The pipeline's workspace doesn't fit public demo papers.**

- Every search filters on one `workspace_id`, but the app has per-user papers plus public demo
  papers, and one query can mix both.
- _Fix (backend-only):_ one constant workspace (`claimlens`), with `paper_id = document_id`. The
  backend checks ownership or `is_public` for every document id before calling the pipeline.
- This also keeps chunk ids stable (they include the workspace id).

## 6. Frontend

**Yes, the React app is on `Main2`** in `frontend/` (React 18 + Vite + TypeScript, commit `a832ed7`
and later). Nothing needs to be brought in.

It already has a first version of Firebase sign-in (`bd9243d`), which Phase 5 will reshape.
Today:

| Area            | Today                                                                 | Phase 5                                      |
| --------------- | --------------------------------------------------------------------- | -------------------------------------------- |
| Session         | App session stored in `sessionStorage`, Firebase SDK loaded on demand | `AuthProvider` with `onAuthStateChanged`     |
| Demo button     | No Firebase account                                                   | `signInAnonymously`                          |
| GitHub button   | Always shown                                                          | Hidden unless `VITE_ENABLE_GITHUB_AUTH=true` |
| Job progress    | `EventSource` without a token; signed-in users fall back to polling   | Stream tickets                               |
| Expired token   | No retry                                                              | Refresh once on 401 and retry                |
| PDF viewer      | No auth header                                                        | Auth header on PDF loads                     |
| Anonymous users | —                                                                     | "Save your work" (`linkWithPopup`)           |

## 7. Proposed folder layout and Python setup

Keep the existing `backend.app` package: the pipelines import from it (G11). Add to it rather
than rename it.

```text
backend/
  app/
    main.py                 create_app() factory + lifespan (Qdrant client, providers, DB)
    config.py               Settings — path kept (imported by both pipelines)
    observability/          logging.py (path kept), request-id middleware, JSON logs
    core/
      errors.py             §4 error shape; validation errors → 400
      security.py           Firebase (Phase 2; today services/firebase_auth.py)
      rate_limit.py         per-uid limits (Phase 2)
    db/
      database.py           connection + migrations (today services/database.py)
      repositories.py       users, documents, chunks, jobs, job_events (today services/runtime.py)
    adapters/
      document_pipeline.py  DocumentPipelineAdapter.process(document_id, pdf_path, on_progress)
                            -> ProcessedDocument(title, pages, chunks); .delete(document_id)
      query_pipeline.py     QueryPipelineAdapter.query / compare / contradiction (on_step)
      providers.py          backend DenseRetriever (G1/G2), SparseRetriever over BM25 (G3),
                            Nemotron GenerationProvider (G10), DB-backed repositories (G8)
    services/
      storage.py            UPLOAD_DIR files, size cap, %PDF- check, sha256
      jobs.py               runner: semaphore, timeout, event fan-out, replay
      citation_guard.py     quote ⊆ chunk text check (whitespace/hyphenation tolerant)
      search/               Semantic Scholar, arXiv, Tavily (Phase 6)
    api/
      deps.py
      routes/               health, me, documents, chunks, jobs, workflows
  requirements.txt          runtime (pip, as today)
  requirements-dev.txt      -r requirements.txt + pytest, pytest-asyncio, ruff
  Dockerfile                Phase 7 (today docker/backend.Dockerfile)
tests/backend/              pytest; mock providers and mock token verification
```

The existing `POST /api/v1/workspaces/{workspace_id}/query` route (`queries.py`) stays as it is.
It belongs to the query pipeline's own contract.

**Python dependency setup.** Same tools as now: no new dependency manager.

- One virtualenv at the repo root (`.venv`, git-ignored), Python 3.12 in Docker; 3.11+ works.
- Install: `pip install -r backend/requirements-dev.txt -r document_pipeline/requirements.txt`.
- Run from the repo root with `PYTHONPATH=.`, because the pipelines import as top-level
  packages (`document_pipeline`, `query_pipeline`, `database`, `backend`).
- **Proposal:** a root `pyproject.toml` holding only `[tool.pytest.ini_options]`
  (`pythonpath = ["."]`, `asyncio_mode = "auto"`) and `[tool.ruff]`, the same style as
  `query_pipeline/pyproject.toml`. Then `pytest` and `ruff` work from the root without
  `PYTHONPATH`. This is a config file, not a new tool.

## 8. Already on `Main2` vs. this plan

Before this plan arrived, three things were built on `Main2`. The phases will reshape them:

| Built (commit)                                                                                                                     | Plan                                                                                                                            | Change in phase |
| ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | --------------- |
| Firebase token check, `GET /api/v1/auth/me`, `FIREBASE_CREDENTIALS_PATH` (`77eb9ee`)                                               | `core/security.py`, `FIREBASE_CREDENTIALS`/`_B64`, `GET /me`, token cache, `ALLOW_ANONYMOUS`, 401 on every protected route      | 2               |
| SQLite store: users, documents with `owner_uid`, chunks, jobs, job_events; requests without a token = shared demo pool (`ac5fdc3`) | `is_public` demo papers, users `display_name`/`is_anonymous`/`last_seen_at`, sha256 dedupe, files in `UPLOAD_DIR`, readable ids | 2–3             |
| Jobs and job events stored in the DB; restart marks running work failed                                                            | Runner with semaphore, timeout, live fan-out, replay, heartbeat, stream tickets                                                 | 4               |

## 9. Pipeline run on a sample PDF

**Setup:**

- PDF: `frontend/src/mocks/pdfs/DOC002.pdf`, the app's own 26-page sample with fictional content.
- No embedding or Nebius keys exist, so steps 3–4 use a fixed local embedding (as their own
  integration test does), Qdrant in local in-memory mode, and their SQLite BM25 index.
- Script: a throwaway script, not committed. I can add it under `scripts/` if you want it kept.

| Step (per their README)                                                      | Result                                                                                                                                                      |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. `ingest_pdf`                                                              | ✅ 26 pages → 26 chunks in ~1.0 s. Title read from the PDF; 8 sections detected (Introduction … Appendix); no chunk spans pages (`page_start == page_end`). |
| 2. `index_pdf` with project settings                                         | ✅ Fails fast as documented: `RuntimeError: Document indexing requires real providers…`. No keys are configured.                                            |
| 3. `ingest_and_embed_pdf` + `index_prepared_paper`                           | ✅ `IndexingResult(qdrant_points=26, bm25_documents=26)`. BM25 search "results accuracy" → pages 8, 9 (Results) and 25 (Appendix).                          |
| 4. `QueryOrchestrator` + their `QdrantDenseRetriever` on that index          | ❌ `AttributeError: 'QdrantClient' object has no attribute 'search'` (G1)                                                                                   |
| 5. `RetrievalCandidate(..., chunk_index=0)`, which the Qdrant adapter builds | ❌ `ValidationError … chunk_index` (G2)                                                                                                                     |
| 6. Orchestrator with their fake dense + sparse retrievers, no reranker       | dense only → `completed` (5 citations); dense + sparse → `insufficient_evidence` (G4)                                                                       |
| Their test suites                                                            | ✅ `query_pipeline`: 12 passed. ✅ `tests/document_pipeline`: 1 passed (needs `pytest-asyncio`).                                                            |

**Verdict:**

- Ingestion → chunks → Qdrant + BM25 works and is ready to wrap.
- The query side can't answer over real indexed data until G1, G2, G4 and G8 are handled, and
  G10 before real Nemotron output can be trusted.
- All four can be handled backend-side (§5) without touching their code.

## 10. Decisions I need from you

1. **Database.** The plan says Postgres + Alembic (Phases 1 and 3); on 2026-10-22 you chose
   SQLite. I'll keep **SQLite with the current versioned migrations**, and the compose file
   gets no `db` service. Alembic on SQLite is possible but adds SQLAlchemy. OK?
2. **G1/G2/G3/G10.** Backend-owned provider classes (no changes to their code). I'd also tell
   the query-pipeline owner about the two Qdrant bugs. OK?
3. **G5 delete.** Ask for (or approve) a small `delete_paper()` on their two indexers, or let the
   adapter delete from Qdrant and `chunks_fts` directly?
4. **G18.** One constant workspace id `claimlens`, with ownership checked by the backend.
5. **§5.** Confirm the adapter shapes in §7, or send me §5.
6. **Keys.** For real runs: the embedding endpoint, model and key; `NEBIUS_API_KEY` and the
   Nemotron model id; and the Firebase service account (as a file or `FIREBASE_CREDENTIALS_B64`).
