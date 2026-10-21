# Research-Paper-Analyzer

The repository now runs as a real frontend/backend application. The frontend
uses the FastAPI API by default; MSW fixtures are enabled only when
`VITE_USE_MOCKS=true` (and remain available to the test suite).

## Frontend (ClaimLens)

The web app lives in [`frontend/`](frontend/) and needs Node 20.19+ or 22.12+.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5174
```

## Backend

Create a Python environment, install the service dependencies, and start the
API from the repository root:

```bash
uv venv
uv pip install --python .venv/bin/python -r backend/requirements.txt -r document_pipeline/requirements.txt
PYTHONPATH=. .venv/bin/uvicorn backend.app.main:app --reload --port 8001
```

Uploads are stored in `storage/researchlens.sqlite3`, processed in the
background through `document_pipeline`, and become queryable only after
successful extraction and indexing. The API exposes document, chunk, query,
job, SSE, compare, and contradiction endpoints under `/api/v1`.

The current query implementation uses deterministic lexical evidence retrieval
so the system works without an LLM. Replace the provider seam in
`backend/app/api/routes/workflows.py` when wiring the generation model; the
document and frontend contracts do not need to change.

### OAuth configuration

Google uses the configured public client ID. GitHub uses the public client ID
`Ov23liz4wXUFCGOKJ6DT`, but GitHub also requires a client secret on the backend.
Set it in the backend environment; never put it in frontend code:

```bash
export GITHUB_CLIENT_SECRET="your-github-oauth-app-secret"
```

Register this GitHub OAuth callback URL:

```text
http://localhost:8001/api/v1/auth/github/callback
```

For a network deployment, replace `localhost` with the public backend URL and
set `FRONTEND_URL` and `BACKEND_URL` accordingly.

## Docker

```bash
docker compose up --build
```

This starts the API on `http://localhost:8001` and the frontend on
`http://localhost:5174`, with document state persisted in a named volume.

See [`frontend/README.md`](frontend/README.md) for frontend scripts and
environment variables, and [`docs/FRONTEND_BUILD_PROMPT.md`](docs/FRONTEND_BUILD_PROMPT.md)
for the original UI build plan.
