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
