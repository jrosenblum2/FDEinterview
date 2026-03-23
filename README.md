# Reducto RAG — Financial Document Assistant

A prototype RAG application for investment advisors. Upload PDFs, ask questions across all documents simultaneously. Documents are parsed by the Reducto API, embedded with Vertex AI, stored in Cloud SQL + pgvector, and answered by Gemini 2.5 Flash.

---

## Project Overview

- **Backend:** Python + FastAPI, served by Uvicorn
- **Frontend:** React (Vite), served as static files by the FastAPI backend in production
- **Database:** PostgreSQL with pgvector on GCP Cloud SQL
- **Document parsing:** Reducto API (chunked + figure-summarised output)
- **Embeddings:** Vertex AI `gemini-embedding-001` (768-dimensional)
- **Generation:** Vertex AI `gemini-2.5-flash` (answers) + `gemini-2.5-flash-lite` (intent classification)
- **Deployment:** Single Docker container on GCP Cloud Run

---

## Prerequisites

The following must be installed and configured before running anything locally:

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) — Python package manager (`pip install uv`)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) — provides the `gcloud` CLI

You also need a GCP project with these APIs enabled and a Cloud SQL PostgreSQL instance. Both are covered in the one-time setup steps in the [Deploying to Cloud Run](#deploying-to-cloud-run) section.

---

## Local Development Setup

### 1. Clone the repo

```bash
git clone <repo-url>
cd FDEinterview
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in all values. See the [Environment Variables](#environment-variables) table for descriptions. Never commit `.env` to version control.

### 3. Authenticate with GCP

Vertex AI calls (embeddings and generation) use your personal GCP credentials in development:

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### 4. Start the Cloud SQL Auth Proxy

The Auth Proxy creates a secure tunnel to your Cloud SQL instance. Download the binary for your platform from [https://cloud.google.com/sql/docs/postgres/connect-auth-proxy](https://cloud.google.com/sql/docs/postgres/connect-auth-proxy) and place it in the project root.

Make the binary executable (first time only):

```bash
chmod +x ./cloud-sql-proxy
```

Start the proxy (leave this running in a dedicated terminal for the duration of your session):

```bash
./cloud-sql-proxy YOUR_PROJECT:YOUR_REGION:YOUR_INSTANCE --port 5432
```

Replace `YOUR_PROJECT:YOUR_REGION:YOUR_INSTANCE` with your `INSTANCE_CONNECTION_NAME` from `.env`.

### 5. Install Python dependencies

Run from the project root:

```bash
uv sync
```

### 6. Install frontend dependencies

```bash
cd frontend && npm install && cd ..
```

---

## Running the App Locally

You need three terminals running simultaneously.

**Terminal 1 — Cloud SQL Auth Proxy** (see step 4 above, keep it running)

**Terminal 2 — FastAPI backend** (run from the project root, not inside `backend/`):

```bash
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8080 --reload
```

You should see `Database tables initialized successfully.` in the logs. If the backend crashes at startup, check that the Auth Proxy is running and your `.env` credentials are correct.

**Terminal 3 — React dev server:**

```bash
cd frontend && npm run dev
```

Open **http://localhost:3000**. The Vite dev server proxies all `/api/*` requests to the backend at port 8080.

### Smoke test

1. Upload a PDF — it should appear in the sidebar with status **complete**
2. Ask a question about the document — an answer with source citations should appear
3. Refresh the page — conversation history should restore automatically
4. Delete the document — it should disappear from the sidebar

---

## Environment Variables

| Variable | Description | Used in |
|---|---|---|
| `ENVIRONMENT` | `development` or `production` — controls database driver | Both |
| `GCP_PROJECT_ID` | GCP project ID | Both |
| `GCP_REGION` | GCP region (e.g. `us-central1`) | Both |
| `DB_NAME` | Cloud SQL database name | Both |
| `DB_USER` | Cloud SQL database user | Both |
| `DB_PASSWORD` | Cloud SQL database password | Both |
| `DB_HOST` | Database host (default `localhost`) | Development only |
| `DB_PORT` | Database port (default `5432`) | Development only |
| `INSTANCE_CONNECTION_NAME` | Cloud SQL connection name (`project:region:instance`) | Production only |
| `REDUCTO_API_KEY` | Reducto API key | Both |
| `VITE_API_URL` | Backend URL for the Vite dev server proxy | Development only |

`VITE_API_URL` is only read by the React dev server. It is not needed in Cloud Run (the frontend is served as static files by the same process as the backend).

---

## Testing with Docker Locally

> **When to use this vs. normal local dev:** Use the normal local dev setup (uvicorn + `npm run dev`) for day-to-day development — backend changes reload instantly and frontend changes appear in the browser via Vite's hot module replacement. Use `dockertest.sh` as a one-time pre-deploy check: it validates that the multi-stage Docker build works, the React app is correctly compiled and served as static files, and the production environment wiring is right. Every code change requires a full image rebuild, so it is too slow for iterative development.

Before deploying to Cloud Run it is useful to run the app inside a Docker container on your machine. This validates the multi-stage build, static file serving, and environment wiring end-to-end — with no separate Vite dev server.

The `dockertest.sh` script handles the full cycle:
- Builds the Docker image from the project root
- Overrides `DB_HOST` to `host.docker.internal` so the container reaches the Auth Proxy on your Mac's localhost
- Mounts your GCP application default credentials for Vertex AI (Cloud Run handles this automatically via the service account)
- Removes and recreates the container on each run so state is always clean

### Prerequisites

- Docker Desktop running
- Cloud SQL Auth Proxy running on port 5432 (same as normal local dev)
- `gcloud auth application-default login` completed

### Run

```bash
# Build the image and start the container
./dockertest.sh

# Skip the build step (faster if only restarting)
./dockertest.sh --no-build
```

Open **http://localhost:8080** — no separate frontend server is needed.

To stream logs from a running container:

```bash
docker logs -f reducto-rag-test
```

---

## Deploying to Cloud Run

Steps 2–6 are one-time setup. Step 1 and step 7 are repeated each session / each deploy.

### 1. Set shell variables

Run at the start of every terminal session you use for deployment. Substitute your real values.

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export INSTANCE=your-cloud-sql-instance-name   # instance name only, not the full connection string
export DB_NAME=your-database-name
export DB_USER=your-database-user
export REPO=reducto-rag
export IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/app
export INSTANCE_CONNECTION_NAME=$PROJECT_ID:$REGION:$INSTANCE
```

### 2. Enable required GCP APIs (once)

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  --project=$PROJECT_ID
```

### 3. Create the Cloud SQL instance and enable pgvector (once)

Create a PostgreSQL instance in Cloud SQL if you don't have one already. After it is running, open **Cloud SQL Studio** in the GCP console, connect to your database, and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

The application tables (`documents`, `chunks`, `chat_history`) are created automatically on first startup.

### 4. Create the Artifact Registry repository (once)

```bash
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION \
  --project=$PROJECT_ID
```

### 5. Authenticate Docker with Artifact Registry (once)

```bash
gcloud auth configure-docker $REGION-docker.pkg.dev
```

### 6. Store secrets in Secret Manager (once)

Cloud Run injects these as environment variables at runtime. Use single quotes around the values to prevent the shell from interpreting special characters.

```bash
echo -n 'your-db-password' | \
  gcloud secrets create db-password --data-file=- --project=$PROJECT_ID

echo -n 'your-reducto-api-key' | \
  gcloud secrets create reducto-api-key --data-file=- --project=$PROJECT_ID
```

To update an existing secret (e.g. after rotating a password):

```bash
echo -n 'new-value' | \
  gcloud secrets versions add db-password --data-file=- --project=$PROJECT_ID
```

> **Important:** Always use `echo -n` (no trailing newline) and single quotes. Double quotes or a missing `-n` flag can embed unexpected characters in the stored value, causing authentication failures at runtime.

### 7. Grant IAM roles to the Cloud Run service account (once)

Cloud Run runs as the Compute Engine default service account. It needs three roles: read secrets, connect to Cloud SQL, and call Vertex AI.

```bash
export SA=$(gcloud iam service-accounts list \
  --filter="displayName:Compute Engine default service account" \
  --format="value(email)" \
  --project=$PROJECT_ID)

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" \
  --role="roles/aiplatform.user"
```

If you already have a service account with these roles, you can skip this step or reuse the existing account by substituting its email address into the `--member` flag above.

### 8. Build, push, and deploy (every release)

> **Apple Silicon (M-series) Mac:** Cloud Run requires a `linux/amd64` image. Use `docker buildx build` with `--platform linux/amd64`. Plain `docker build` on ARM Macs produces an ARM image that Cloud Run rejects. The `--push` flag builds and pushes in one step.

```bash
docker buildx build --platform linux/amd64 -t $IMAGE --push .

gcloud run deploy reducto-rag \
  --image=$IMAGE \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="ENVIRONMENT=production,GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,INSTANCE_CONNECTION_NAME=$INSTANCE_CONNECTION_NAME,DB_NAME=$DB_NAME,DB_USER=$DB_USER" \
  --set-secrets="DB_PASSWORD=db-password:latest,REDUCTO_API_KEY=reducto-api-key:latest" \
  --add-cloudsql-instances=$INSTANCE_CONNECTION_NAME \
  --project=$PROJECT_ID
```

`ENVIRONMENT=production` switches the database driver from psycopg2 (Auth Proxy) to pg8000 (Cloud SQL Python Connector). Vertex AI authentication uses the service account automatically — no credentials file is needed.

Once the deploy completes, the command prints the service URL. Open it in a browser to verify the app is live.

To stream logs from the running service:

```bash
gcloud run services logs read reducto-rag --region=$REGION --project=$PROJECT_ID --limit=50
```

---

## Agentic Pipeline Architecture

Every user message passes through a four-step agentic pipeline in `orchestrator.py`:

```
User message
     │
     ▼
[1] Intent Classification  (generation.py — gemini-2.5-flash-lite)
     │  Classifies intent as "query" or "out_of_scope"
     │  Returns a refined, retrieval-optimised version of the query
     │  Identifies which uploaded documents are most likely relevant
     │
     ▼ (if "query")
[2] Query Embedding  (embeddings.py)
     │  Embed the refined query with gemini-embedding-001
     │
     ▼
[3] Chunk Retrieval  (retrieval.py)
     │  Cosine similarity search against pgvector
     │  Filtered to the relevant documents identified in step 1
     │  Returns top-25 most similar chunks + document metadata
     │
     ▼
[4] Answer Generation  (generation.py — gemini-2.5-flash)
     │  Gemini evaluates whether the chunks are sufficient to answer
     │  If sufficient  → generates a grounded answer, cites which chunks it used
     │  If insufficient → explains what information is missing and suggests
     │                    related questions the documents can answer
     ▼
Answer + Source Citations → Frontend
```

Document uploads run a separate pipeline:

```
PDF upload → MD5 deduplication → Reducto parse → Batch embedding → Store chunks
```
