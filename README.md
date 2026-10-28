# Research-Paper-Analyzer

Full-stack research-paper RAG application with a FastAPI backend, NVIDIA
Nemotron generation, NVIDIA embeddings, Qdrant retrieval, BM25 indexing, and
the ClaimLens React frontend.

## Requirements

- Python 3.12+
- Node.js 20.19+ or 22.12+
- Docker Desktop for local Qdrant
- NVIDIA API credentials for live providers

## Configure

```bash
cp .env.example .env
```

For live RAG, set these values in `.env`:

```dotenv
APP_ENV=development
USE_FAKE_PROVIDERS=false
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_API_KEY=your_nvidia_api_key
NVIDIA_MODEL=nvidia/nemotron-3-ultra-550b-a55b
EMBEDDING_BASE_URL=https://integrate.api.nvidia.com/v1
EMBEDDING_API_KEY=your_nvidia_api_key
EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b
EMBEDDING_DIMENSION=2048
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=paper_chunks
BM25_INDEX_PATH=storage/bm25/index.sqlite3
```

Never commit `.env` or API keys. The example files contain placeholders only.

## Install backend

```bash
uv venv .venv
uv pip install --python .venv/bin/python \
  -r backend/requirements.txt \
  -r query_pipeline/requirements.txt \
  -r document_pipeline/requirements.txt
```

## Start Qdrant

Start Docker Desktop, then run:

```bash
docker run --rm --name research-paper-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  qdrant/qdrant:latest
```

## Start the backend

In another terminal:

```bash
.venv/bin/uvicorn backend.app.main:app \
  --reload --host 0.0.0.0 --port 8000
```

Backend URLs:

- API: <http://localhost:8000>
- Swagger: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

## Start the frontend

In a third terminal:

```bash
cd frontend
npm ci
```

For mock mode, which does not need Qdrant or NVIDIA:

```bash
npm run dev -- --host 0.0.0.0
```

For the real backend, create `frontend/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_USE_MOCKS=false
VITE_ENABLE_CLAIM_MODE=true
VITE_ENABLE_FETCH_BY_LINK=true
```

Then start the frontend:

```bash
npm run dev -- --host 0.0.0.0
```

Open <http://localhost:5173>.

## End-to-end live flow

1. Start Qdrant, the backend, and the frontend in separate terminals.
2. Open the Library page and upload a PDF.
3. The backend extracts text, chunks the paper, calls NVIDIA embeddings,
   writes vectors to Qdrant and documents to BM25, then marks the paper ready.
4. Select the ready paper and open Ask.
5. The query is embedded, retrieved, filtered, and passed with evidence to
   NVIDIA Nemotron.
6. The validated answer, claims, uncertainties, and citations are returned
   through the API/job or workspace SSE flow.

Without indexed ready papers, the backend returns `no_ready_papers` safely.

## Validation

Backend:

```bash
.venv/bin/python -m compileall -q backend database query_pipeline document_pipeline
.venv/bin/pytest query_pipeline/tests -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Useful endpoints

```text
GET  /health
GET  /api/v1/documents
POST /api/v1/upload
POST /api/v1/workspaces/{workspace_id}/query
POST /api/v1/workspaces/{workspace_id}/query/stream
POST /api/v1/query
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs/{job_id}/stream
```

## Project layout

```text
backend/            FastAPI application and API routes
database/           Repository implementations
document_pipeline/  PDF ingestion, chunking, embeddings, and indexing
query_pipeline/     RAG orchestration, providers, schemas, and tests
frontend/           ClaimLens Vite/React application
```

See [`frontend/README.md`](frontend/README.md) for frontend scripts and
[`query_pipeline/README.md`](query_pipeline/README.md) for pipeline details.
