# ClaimLens API and the services it uses

The backend is a FastAPI app (`backend/`) that connects the React frontend (`frontend/`) to
the teammates' **Document Pipeline** (`document_pipeline/`) and **Query Pipeline**
(`query_pipeline/`). Their code is used as it is; the backend implements their provider and
repository interfaces in `backend/app/adapters/`.

```text
React (Firebase JS SDK: sign in → ID token)
   │  HTTPS, Authorization: Bearer <Firebase ID token>   (no token = the shared demo)
   ▼
FastAPI  backend/app
   ├─ Auth: Firebase Admin SDK verifies the token → uid; documents and jobs belong to a uid
   ├─ Documents ─► DocumentPipelineAdapter ─► ingest_pdf → embed_chunks → index_prepared_paper
   │                                           (vectors in SQLite, BM25 in SQLite FTS5)
   ├─ Jobs + SSE ─► QueryPipelineAdapter ──► QueryOrchestrator.run (Ask) and the same
   │                                           retrieval for Compare / Conflicts / Check
   ├─ Citation guard: every quote is re-checked against its chunk's stored text
   ├─ Claim check: Semantic Scholar + arXiv + Tavily → open-access PDFs → pipeline → judge
   └─ SQLite: users, documents, chunks, chunk vectors, jobs, job steps
```

## External APIs

| API                                        | Used for                                                                                                                           | Endpoint                                                                                                                                                    | Key (env var)                                                                          | Without the key                                                |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Firebase Authentication**                | Sign-in in the browser (email/password, Google, GitHub) and verifying ID tokens on the server                                      | Firebase JS SDK; Firebase Admin SDK `verify_id_token`; Identity Toolkit REST `accounts:signInWithPassword` (Postman only)                                   | Frontend `VITE_FIREBASE_*`; backend `FIREBASE_CREDENTIALS_PATH` (service-account JSON) | Only the account-free demo works; token requests get 503       |
| **NVIDIA API Catalog — embeddings**        | Vectors for every chunk and every question (dense retrieval)                                                                       | `POST {EMBEDDING_BASE_URL}/embeddings`, OpenAI-compatible, with `input_type: passage/query` and `truncate: END` for NVIDIA retrieval models                 | `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`    | Local hashing embeddings (lexical, not semantic)               |
| **Nebius Token Factory — NVIDIA Nemotron** | Writing answers with cited claims, Compare cells, finding conflicts, judging claim evidence, rewriting a claim into search queries | `POST {NEBIUS_BASE_URL}/chat/completions`, OpenAI-compatible, JSON mode                                                                                     | `NEBIUS_API_KEY`, `NEBIUS_MODEL`                                                       | Extractive answers (quoted sentences) and heuristic judgements |
| **Semantic Scholar Graph API**             | Claim check search; resolving DOIs and Semantic Scholar links for “Fetch by link”                                                  | `GET https://api.semanticscholar.org/graph/v1/paper/search?openAccessPdf`; `GET /graph/v1/paper/{id}` and `/paper/DOI:{doi}`                                | `SEMANTIC_SCHOLAR_API_KEY` (optional, raises the rate limit)                           | Works keyless, but the shared pool is often rate-limited (429) |
| **arXiv API**                              | Claim check search; titles and authors for arXiv links                                                                             | `GET https://export.arxiv.org/api/query` (`search_query`, `id_list`), at most one call every 3 s                                                            | none                                                                                   | —                                                              |
| **Tavily Search**                          | Claim check web search restricted to paper sites                                                                                   | `POST https://api.tavily.com/search` (`search_depth: basic`, `include_domains`)                                                                             | `TAVILY_API_KEY`                                                                       | Skipped; the trace says so                                     |
| **Open-access PDF hosts**                  | Downloading papers found by search or pasted as links                                                                              | HTTPS GET to allowlisted hosts (arxiv.org, aclanthology.org, openreview.net, …); same-host redirects only; 25 MB cap; 30 s timeout; must start with `%PDF-` | `DOWNLOAD_ALLOWED_HOSTS` adds hosts                                                    | —                                                              |

All model and search output is treated as untrusted data: it is parsed and checked, never
executed or used in file paths. Prompts tell the model that passages are data, not
instructions, and every quote it returns must appear in the stored chunk text.

## The teammates' pipelines (Python APIs used, unchanged)

| Their function / class                                                                           | Called by the backend for                                                                                                                        |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `document_pipeline.ingestion.ingest_pdf`                                                         | Extracting text, sections and page-aware chunks from each PDF                                                                                    |
| `document_pipeline.embeddings.embed_chunks`                                                      | Embedding the chunks (with our NVIDIA or local embedder) and validating each vector                                                              |
| `document_pipeline.pipeline.index_prepared_paper`                                                | Writing vectors (our `SQLiteVectorIndexer`) and BM25 text (their `BM25Indexer`)                                                                  |
| `document_pipeline.indexing.BM25Indexer`                                                         | The SQLite FTS5 keyword index and its `search`                                                                                                   |
| `query_pipeline...QueryOrchestrator.run`                                                         | Ask: validation, retrieval, rank fusion, reranking, dedupe, evidence balancing, context compression, source ids, generation and citation mapping |
| `reciprocal_rank_fusion`, `deduplicate`, `QueryRequest`, `RetrievalCandidate`, `GeneratedAnswer` | Shared retrieval for Compare, Conflicts and claim checks                                                                                         |

The backend supplies the interfaces their orchestrator expects (`backend/app/adapters/providers.py`):
`SQLiteDenseRetriever` (cosine search over vectors stored in SQLite), `BM25SparseRetriever`,
`TermReranker`, Nemotron or extractive `GenerationProvider`s, and paper/chunk repositories
backed by the backend database. No vector database server is needed.

## REST endpoints

Base URL: `http://localhost:8001/api/v1` (Docker and `npm run dev` use this). Every request
may send `Authorization: Bearer <Firebase ID token>`. Without a token the request belongs to
the shared demo; a token that is sent but invalid is a 401. A signed-in user only sees their
own documents and jobs; anything else is a 404.

| Method & path                | Body                                                                                      | Success                                                         | Notes                                                                                                                                                                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /health` (no `/api/v1`) | —                                                                                         | `{"status": "ok"}`                                              | Liveness for Docker                                                                                                                                                                                                                   |
| `GET /health`                | —                                                                                         | `{status, version, mock_ai, checks}`                            | `mock_ai` is true while a local fallback replaces NVIDIA embeddings or Nemotron                                                                                                                                                       |
| `GET /auth/me`               | —                                                                                         | `{user: {id, email, name, picture, provider}}`                  | Requires a token; saves the profile                                                                                                                                                                                                   |
| `POST /upload`               | multipart `files`: 1–5 PDFs, ≤ 25 MB each                                                 | `202 [{document_id, filename, status}]`                         | Checks the `%PDF-` signature; the same file again returns the existing document                                                                                                                                                       |
| `GET /documents`             | `?status=processing\|ready\|failed`                                                       | `Document[]`                                                    | `{document_id, title, filename, authors?, year?, pages, chunks, status, source, url?, progress, error, uploaded_at}`                                                                                                                  |
| `GET /documents/{id}`        | —                                                                                         | `{document_id, status, pages, chunks, sections[], error}`       | Poll while `processing`; `progress` is 0–100 in the list                                                                                                                                                                              |
| `GET /documents/{id}/file`   | —                                                                                         | PDF bytes (inline)                                              |                                                                                                                                                                                                                                       |
| `DELETE /documents/{id}`     | —                                                                                         | `204`                                                           | Removes the file, chunks, vectors and BM25 rows                                                                                                                                                                                       |
| `POST /documents/fetch`      | `{url}`: arXiv URL, DOI, Semantic Scholar link or allowlisted PDF link                    | `202 Document`                                                  | Downloads and processes in the background                                                                                                                                                                                             |
| `POST /documents/{id}/retry` | —                                                                                         | `202 Document`                                                  | Re-processes a failed (or stale) paper                                                                                                                                                                                                |
| `GET /chunks/{chunk_id}`     | —                                                                                         | `{chunk_id, document_id, page, section, text, title}`           | The text the citation guard checks against                                                                                                                                                                                            |
| `POST /query`                | `{question, document_ids[1..20]}`                                                         | `202 {job_id}`                                                  | Result `QueryResult`: `{answer, claims[{claim, status, confidence, evidence[]}], highlights}`; `[n]` in the answer is the n-th paper of `document_ids`                                                                                |
| `POST /compare`              | `{document_ids[2..10], attributes?[]}`                                                    | `202 {job_id}`                                                  | Result `CompareRow[]`; default attributes: Method, Base model, Benchmark, Metric, Headline result, Code released                                                                                                                      |
| `POST /contradiction`        | `{document_ids[2..10], topic?}`                                                           | `202 {job_id}`                                                  | Result `Contradiction[]` with both quotes, status, explanation, factors                                                                                                                                                               |
| `POST /check`                | `{claim, max_papers? (1–10, default 6), sources?: ["semantic_scholar","arxiv","tavily"]}` | `202 {job_id}`                                                  | Result `CheckResult`: papers, supports/contradicts/partial/insufficient evidence, summary, `verified_quotes`/`total_quotes`, `sources[{name, count}]`. Falls back to the caller's ready papers when nothing can be downloaded         |
| `GET /jobs/{id}`             | —                                                                                         | `{job_id, kind, status: running\|done\|error, result?, error?}` |                                                                                                                                                                                                                                       |
| `GET /jobs/{id}/stream`      | —                                                                                         | Server-Sent Events                                              | Replays every `step {type, message, via?, t}`, then `done {result}` or `error {error}`; heartbeat comments every 15 s. EventSource cannot send a token, so a signed-in user's stream is a 404 and the frontend polls `GET /jobs/{id}` |

Evidence items are `{chunk_id, document_id, page, section, quote, highlight, note?}`. Step
types, in order: `searching`, `processing` (check only), `retrieving`, `reranking`,
`reasoning`, `validating`.

Errors always use `{"error": {"code": string, "message": string}}`:

| Status | Code                  | When                                                                    |
| ------ | --------------------- | ----------------------------------------------------------------------- |
| 400    | `INVALID_REQUEST`     | Invalid body or query (validation errors are 400, not 422), bad link    |
| 401    | `UNAUTHENTICATED`     | Token missing on `/auth/me`, or invalid / expired                       |
| 404    | `NOT_FOUND`           | Unknown id, or another user's document or job                           |
| 409    | `DOCUMENT_NOT_READY`  | A selected paper is still processing or failed                          |
| 413    | `FILE_TOO_LARGE`      | A PDF over 25 MB                                                        |
| 415    | `UNSUPPORTED_TYPE`    | Not a PDF                                                               |
| 502    | `UPSTREAM_ERROR`      | (in a job's `error`) a model or search API failed, or the job timed out |
| 503    | `SERVICE_UNAVAILABLE` | Firebase is not configured on the server                                |
| 500    | `INTERNAL_ERROR`      | Anything unexpected                                                     |

## What works without any keys

Everything. Uploads are chunked by the document pipeline, embedded with local hashing
embeddings and indexed; Ask runs the real query orchestrator and answers with quoted
sentences; Compare, Conflicts and Check use extractive and heuristic fallbacks. `GET /health`
reports `mock_ai: true` until `EMBEDDING_*` and `NEBIUS_*` are set. Changing the embedding
model later needs each paper re-processed (`POST /documents/{id}/retry`), because vectors
from different models are not compared.

## Testing with Postman

1. Start the backend (`PYTHONPATH=. uvicorn backend.app.main:app --port 8001`).
2. In Postman, **Import** `docs/postman/ClaimLens.postman_collection.json`.
3. Run **Health**, then **Documents › Upload PDFs** after choosing one or two PDFs in the
   request's _Body_ tab. The test scripts save `documentId`, `jobId` and `chunkId` in the
   collection variables for the next requests.
4. Repeat **Get one document** until `status` is `ready`, then run any request in
   **Analysis jobs** and repeat **Get job** until `done`.
5. To test as a signed-in user, set `firebaseApiKey`, `firebaseEmail` and
   `firebasePassword` in the collection variables and run **Auth › Firebase sign-in**; it
   stores `idToken`, which every request then sends. Leave `idToken` empty for the demo.

The same collection runs from the command line with Newman:
`npx newman run docs/postman/ClaimLens.postman_collection.json` (choose the upload files in
Postman first, or edit their `src` paths).
