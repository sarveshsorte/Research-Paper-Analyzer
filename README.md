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

Copy `.env.example` to `.env` and add the keys you have. The app works end to
end without any: local embeddings stand in for NVIDIA's and answers quote the
papers directly. With keys it uses:

- **NVIDIA API Catalog embeddings** (`EMBEDDING_*`) for semantic retrieval;
- **NVIDIA Nemotron on Nebius Token Factory** (`NEBIUS_API_KEY`, `NEBIUS_MODEL`)
  for answers, comparisons, conflicts and claim judgements;
- **Semantic Scholar, arXiv and Tavily** (`TAVILY_API_KEY`, optional
  `SEMANTIC_SCHOLAR_API_KEY`) to find open-access papers for claim checks.

`GET /api/v1/health` shows which of these are active.

How a paper flows: an upload (or a pasted arXiv/DOI/Semantic Scholar link, or a
paper found by a claim check) runs through the teammates' `document_pipeline`
(`ingest_pdf` → `embed_chunks` → `index_prepared_paper`). Chunks and their
vectors are stored in SQLite (`STORAGE_PATH`) and the text in the pipeline's
BM25 index (`BM25_INDEX_PATH`); no vector database server is needed. Questions
run through the teammates' `QueryOrchestrator`; Compare, Conflicts and claim
checks reuse the same retrieval. Every quote returned is re-checked against its
chunk's stored text. The adapters live in `backend/app/adapters/`; the
pipelines' own code is unchanged.

The database holds users, documents, chunks, chunk vectors, jobs and job steps.
It is created on first start and upgraded automatically when the schema changes
(`backend/app/services/database.py`). Documents and jobs belong to the Firebase
user who created them: a signed-in user only sees their own. Requests without a
token are the live demo, which shares one pool of documents. Jobs survive a
restart; uploads or jobs still running when the server stopped are marked
failed. The API runs as a single process (SQLite).

**API reference:** [`docs/api.md`](docs/api.md) lists every endpoint and every
external API used. A Postman collection for testing them all is in
[`docs/postman/ClaimLens.postman_collection.json`](docs/postman/ClaimLens.postman_collection.json).

### Sign-in (Firebase Authentication)

Accounts use Firebase Authentication: email and password, Google and GitHub.
**Try the live demo** needs no account and works without any of this.

1. In the [Firebase console](https://console.firebase.google.com/), create a
   project and, under **Authentication > Sign-in method**, enable
   Email/Password, Google and GitHub. GitHub needs an OAuth app whose callback
   URL is the one Firebase shows on that screen.
2. Under **Authentication > Settings > Authorized domains**, make sure
   `localhost` (and any deployed domain) is listed.
3. Frontend: register a web app under **Project settings > Your apps** and copy
   its config into `frontend/.env`:

   ```bash
   VITE_FIREBASE_API_KEY=...
   VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
   VITE_FIREBASE_PROJECT_ID=your-project
   VITE_FIREBASE_APP_ID=...
   ```

   These values identify the project; they are not secrets.

4. Backend: under **Project settings > Service accounts**, generate a private
   key and save it as `secrets/firebase-service-account.json` (the `secrets/`
   folder is git-ignored). Then set, in the root `.env`:

   ```bash
   FIREBASE_CREDENTIALS_PATH=secrets/firebase-service-account.json
   FIREBASE_PROJECT_ID=your-project
   ```

   The service-account key is a secret: never commit it or put it in frontend
   code. Without it, `GET /api/v1/auth/me` answers 503 and account sign-in
   shows that Firebase is not configured.

After Firebase signs a user in, the frontend calls `GET /api/v1/auth/me` with
the Firebase ID token as `Authorization: Bearer <token>`; the backend verifies
it with `firebase-admin`. Signed-in API calls send a fresh ID token the same way.

### Backend tests

```bash
uv pip install --python .venv/bin/python -r backend/requirements-dev.txt -r document_pipeline/requirements.txt
.venv/bin/python -m pytest tests
```

## Docker

```bash
docker compose up --build
```

This starts the API on `http://localhost:8001` and the frontend on
`http://localhost:5174`, with document state persisted in a named volume.
For account sign-in, put the `VITE_FIREBASE_*` and `FIREBASE_PROJECT_ID`
values in the root `.env` (Compose reads it) and the service-account key in
`secrets/firebase-service-account.json`, which is mounted read-only.

See [`frontend/README.md`](frontend/README.md) for frontend scripts and
environment variables, and [`docs/FRONTEND_BUILD_PROMPT.md`](docs/FRONTEND_BUILD_PROMPT.md)
for the original UI build plan.
