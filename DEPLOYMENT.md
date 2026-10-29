# 🚀 Deploying ClaimLens (Render + Vercel + Qdrant Cloud)

This guide walks you through deploying **ClaimLens** using the **Free / Low-Cost PaaS stack**:
- **Frontend**: [Vercel](https://vercel.com) (Free Tier, Global CDN, Auto SSL)
- **Backend API**: [Render](https://render.com) (Free / Hobby Docker Web Service)
- **Vector DB**: [Qdrant Cloud](https://cloud.qdrant.io) (Free 1 GB Cluster) or Render Persistent Disk
- **LLM / Embeddings / Reranker**: NVIDIA Build API

---

## 📋 Prerequisites Checklist

Before you begin, have the following ready:
1. **GitHub Account**: Your ClaimLens repository pushed to GitHub.
2. **NVIDIA API Keys**:
   - `NVIDIA_API_KEY` (for embeddings & Nemotron generation)
   - `RERANKER_API_KEY` (for Nemotron-3.5-Rerank-8B)
3. **Free Accounts**:
   - [Vercel](https://vercel.com/signup)
   - [Render](https://dashboard.render.com/register)
   - *(Optional)* [Qdrant Cloud](https://cloud.qdrant.io) (1 GB Free Forever)

---

## 🛠️ Step 1: Push Code to GitHub

Ensure all new deployment files are committed and pushed to your GitHub repository:
```bash
git add .
git commit -m "feat: configure production deployment for Render and Vercel"
git push origin main
```

---

## ⚡ Step 2: Deploy Backend to Render

1. Log into your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** → **Web Service**.
3. Select **Build and deploy from a Git repository** and connect your GitHub repo.
4. Fill in the service configuration:
   - **Name**: `claimlens-backend` (or your choice)
   - **Region**: Choose the closest region (e.g. Oregon, Frankfurt, Singapore)
   - **Branch**: `main`
   - **Runtime**: **Docker** (Render will automatically detect the root `Dockerfile`)
   - **Instance Type**: **Free** (or Starter for no cold-starts)
5. Add the **Environment Variables** under **Environment**:

| Key | Value | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `production` | Enables production mode |
| `USE_FAKE_PROVIDERS` | `false` | Uses live NVIDIA models |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | NVIDIA endpoint |
| `NVIDIA_API_KEY` | `nvapi-...` | Your NVIDIA API key |
| `NVIDIA_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` | Generation model |
| `EMBEDDING_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Embedding endpoint |
| `EMBEDDING_API_KEY` | `nvapi-...` | Your embedding API key |
| `EMBEDDING_MODEL` | `nvidia/nemotron-3-embed-1b` | Embedding model |
| `EMBEDDING_DIMENSION` | `2048` | Embedding dimension |
| `RERANKER_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Reranker endpoint |
| `RERANKER_API_KEY` | `nvapi-...` | Your reranker API key |
| `RERANKER_MODEL` | `nvidia/nemotron-3.5-rerank-8b` | Nemotron reranker |
| `QDRANT_COLLECTION` | `paper_chunks` | Collection name |
| `BM25_INDEX_PATH` | `storage/bm25/index.sqlite3` | SQLite index path |
| `CORS_ORIGINS` | `http://localhost:5173,https://*.vercel.app` | Allowed CORS origins |

6. *(Optional but Recommended for Free Tier)* **Persistent Disk**:
   - Scroll down to **Disks** → Click **Add Disk**:
     - **Name**: `claimlens-storage`
     - **Mount Path**: `/app/storage`
     - **Size**: `1 GB`
   *(This ensures uploaded PDFs and BM25 index persist across restarts).*

7. Click **Create Web Service**.
8. Render will build the Docker container and deploy it. Once ready, copy your backend URL:
   `https://claimlens-backend.onrender.com`

> **Note on Render Free Tier Cold Starts**: Render's free tier spins down after 15 minutes of inactivity. When a request comes in, it takes ~30-50 seconds to wake up.

---

## 🎨 Step 3: Deploy Frontend to Vercel

1. Log into your [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** → **Project**.
3. Import your **Research-Paper-Analyzer** GitHub repository.
4. In the **Configure Project** screen:
   - **Project Name**: `claimlens` (or your choice)
   - **Framework Preset**: **Vite**
   - **Root Directory**: Click *Edit* and select **`frontend`**
   - **Build Command**: `npm run build` (default)
   - **Output Directory**: `dist` (default)
5. Expand **Environment Variables** and add:

| Key | Value |
| :--- | :--- |
| `VITE_API_BASE_URL` | `https://<your-render-app-name>.onrender.com/api/v1` |
| `VITE_USE_MOCKS` | `false` |
| `VITE_ENABLE_CLAIM_MODE` | `true` |
| `VITE_ENABLE_FETCH_BY_LINK` | `true` |

6. Click **Deploy**.
7. Vercel will build and deploy your frontend in ~45 seconds. You will get a live URL:
   `https://claimlens.vercel.app` (or similar).

---

## 🗄️ Step 4: (Optional) Setting up Qdrant Cloud (Free 1GB)

If you prefer managed cloud vector storage over local embedded storage:
1. Sign up at [cloud.qdrant.io](https://cloud.qdrant.io).
2. Click **Create Cluster** → Choose **Free Tier** (1GB RAM, 0.5 vCPU, forever free).
3. Once created, copy the **Cluster URL** (e.g. `https://xyz.us-east4-0.gcp.cloud.qdrant.io:6333`).
4. Generate an **API Key** under Data Access Control.
5. In your Render Dashboard, add/update these two environment variables:
   - `QDRANT_URL`: `https://xyz.us-east4-0.gcp.cloud.qdrant.io:6333`
   - `QDRANT_API_KEY`: `<your-qdrant-api-key>`
6. Render will automatically redeploy with Qdrant Cloud connected.

---

## ✅ Step 5: Verification & Testing

Once both services are deployed:
1. **Verify Backend Health**:
   Visit `https://<your-backend>.onrender.com/health` in your browser.
   It should return:
   ```json
   {"status": "ok", "service": "query_service"}
   ```
2. **Verify Swagger API Docs**:
   Visit `https://<your-backend>.onrender.com/docs` to test endpoints interactively.
3. **Verify Frontend**:
   Open your Vercel URL `https://<your-frontend>.vercel.app`.
   - The brand entry animation will play.
   - Go to **Library** and upload or fetch a research paper by arXiv URL.
   - Test **Ask**, **Compare**, **Conflicts**, and **Check**!
