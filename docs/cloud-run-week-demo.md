# Cloud Run One-Week Demo Deployment

This runbook is scoped for a private one-week demo for 5-6 users. It keeps the architecture small, cost-controlled, and close to the local implementation:

- Cloud Run backend: FastAPI Graph RAG API.
- Cloud Run frontend: Next.js UI.
- Cloud SQL for PostgreSQL: persistent documents, skills, traces, graph payload snapshots.
- Neo4j AuraDB: graph persistence.
- GCS buckets: raw/document artifact bucket references.
- LlamaParse Agentic: PDF parsing.
- Gemini Embedding 2: embeddings.
- Vertex semantic ranker: reranking.
- OpenAI `gpt-5.4-mini`: routing and answer synthesis.

## Deployment Shape

Use two Cloud Run services:

| Service | Name | Public | Notes |
| --- | --- | --- | --- |
| Backend | `cogniz-graphrag-api` | Yes, protected by `x-api-key` | Attach Cloud SQL instance. Configure CORS to frontend URL only. |
| Frontend | `cogniz-graphrag-web` | Yes | Built with backend URL and demo API key. |

For a small interview/demo group:

- Backend: `2Gi`, `2 CPU`, `concurrency=10`, `max-instances=2`, `timeout=900`.
- Frontend: `1Gi`, `1 CPU`, `concurrency=20`, `max-instances=2`, `timeout=300`.
- Keep `min-instances=0` to reduce cost. First request may be cold.
- Do not allow arbitrary CORS origins.
- Use one strong shared demo key for the week and rotate/delete it after.

## Env And Secret Source

The deploy script reads the root `.env` and generates Cloud Run env files under:

```text
deploy/cloudrun/generated/
```

Those generated files are git-ignored. Do not hand-copy placeholder env files for the real deploy path.

Secret values are read from root `.env` and written to Secret Manager:

- `API_AUTH_KEY` -> `api-auth-key`
- `OPENAI_API_KEY` -> `openai-api-key`
- `GEMINI_API_KEY` -> `gemini-api-key`
- `LLAMA_CLOUD_API_KEY` -> `llama-cloud-api-key`
- `NEO4J_PASSWORD` -> `neo4j-password`

Non-secret runtime env values are generated from root `.env`, including Cloud SQL socket URL, Neo4j URI, bucket names, model names, parser settings, embedding settings, and reranker settings.

## Cloud Prerequisites

Set common values:

```bash
export PROJECT_ID=criteo-e6e97
export REGION=us-central1
export REPOSITORY=cognizinterview
export BACKEND_SERVICE=cogniz-graphrag-api
export FRONTEND_SERVICE=cogniz-graphrag-web
export CLOUD_SQL_INSTANCE=free-trial-first-project
export CLOUD_SQL_CONNECTION_NAME="${PROJECT_ID}:${REGION}:${CLOUD_SQL_INSTANCE}"
```

Enable APIs:

```bash
gcloud config set project "$PROJECT_ID"
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  storage.googleapis.com
```

Create Artifact Registry:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --repository-format docker \
  --location "$REGION" \
  --description "CognizInterview Graph RAG demo images"
```

If it already exists, the create command can be skipped.

## Secrets

The deploy script creates or updates these Secret Manager secrets from root `.env`:

```text
api-auth-key
openai-api-key
gemini-api-key
llama-cloud-api-key
neo4j-password
```

Grant the Cloud Run runtime service account access if you use a custom service account. With the default compute service account, adjust the member below:

```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for secret in api-auth-key openai-api-key gemini-api-key llama-cloud-api-key neo4j-password; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${RUN_SA}" \
    --role roles/secretmanager.secretAccessor
done
```

## IAM For Backend

The backend service account needs:

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/cloudsql.client

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/storage.objectAdmin

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/discoveryengine.viewer

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member "serviceAccount:${RUN_SA}" \
  --role roles/aiplatform.user
```

For this app, Vertex reranking uses the Discovery Engine Ranking API endpoint and ADC from the Cloud Run runtime.

## Cloud SQL

Use the existing Cloud SQL PostgreSQL instance. Confirm database/user:

```bash
gcloud sql instances describe "$CLOUD_SQL_INSTANCE" --format='value(connectionName)'
gcloud sql databases list --instance "$CLOUD_SQL_INSTANCE"
gcloud sql users list --instance "$CLOUD_SQL_INSTANCE"
```

For Cloud Run, `DATABASE_URL` is generated from `DATABASE_URL_CLOUD_RUN` in root `.env`. It must use the Unix socket form:

```text
postgresql+asyncpg://graphrag_app:PASSWORD@/graphrag?host=/cloudsql/PROJECT:REGION:INSTANCE
```

The app creates its own application tables at first use.

## CORS

Cloud CORS must be explicit.

Backend env:

```yaml
APP_ENV: "cloud"
CORS_ALLOWED_ORIGINS: "https://YOUR_FRONTEND_SERVICE_URL"
```

Localhost is only allowed when `APP_ENV=local`.

The deploy script handles the order:

1. Deploy backend with empty `CORS_ALLOWED_ORIGINS`.
2. Deploy frontend using the real backend URL.
3. Read the real frontend URL.
4. Regenerate backend env with `CORS_ALLOWED_ORIGINS` set to the frontend URL.
5. Redeploy backend.

This avoids `allow_origins=["*"]` with credentials/API keys.

## Build And Deploy

Run:

```bash
./scripts/deploy-cloudrun.sh
```

The script:

1. Enables required services.
2. Creates Artifact Registry if missing.
3. Builds backend image with Cloud Build.
4. Deploys backend with Cloud SQL attached and Secret Manager values.
5. Reads backend URL.
6. Builds frontend image with the real `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_DEMO_API_KEY`.
7. Deploys frontend.
8. Redeploys backend with exact frontend CORS.

## Smoke Test

Set deployed URLs:

```bash
export BACKEND_URL="$(gcloud run services describe "$BACKEND_SERVICE" --region "$REGION" --format='value(status.url)')"
export FRONTEND_URL="$(gcloud run services describe "$FRONTEND_SERVICE" --region "$REGION" --format='value(status.url)')"
set -a
source .env
set +a
```

Backend:

```bash
curl -H "x-api-key: $API_AUTH_KEY" "$BACKEND_URL/v1/chat/ready"
curl -H "x-api-key: $API_AUTH_KEY" "$BACKEND_URL/v1/documents/ready"
curl -H "x-api-key: $API_AUTH_KEY" "$BACKEND_URL/v1/traces/admin/smoke"
```

CORS preflight:

```bash
curl -i -X OPTIONS "$BACKEND_URL/v1/documents" \
  -H "Origin: $FRONTEND_URL" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-api-key"
```

Expected headers include:

```text
access-control-allow-origin: https://FRONTEND_SERVICE_URL
access-control-allow-headers: ...
```

Streaming:

```bash
curl --no-buffer \
  -H "x-api-key: $API_AUTH_KEY" \
  -H "content-type: application/json" \
  -X POST "$BACKEND_URL/v1/chat/stream" \
  -d '{"message":"hello"}'
```

Frontend:

Open the frontend URL, upload a small PDF, wait for ingestion, ask a question, then inspect `/trace`.

## Operational Guardrails

For a one-week demo:

- Use a strong temporary `API_AUTH_KEY`.
- Share only the frontend URL, not raw backend docs unless needed.
- Leave `max-instances=2` to cap spend.
- Do not upload large confidential documents unless the GCP project and Neo4j tenancy are approved for that data.
- Rotate/delete the demo key after the week.
- Delete Cloud Run services or set max instances to 0 after the demo.
- Monitor Cloud Run logs for parse failures and API quota errors.

## Cleanup

Pause app access:

```bash
gcloud run services update "$FRONTEND_SERVICE" --region "$REGION" --no-allow-unauthenticated
gcloud run services update "$BACKEND_SERVICE" --region "$REGION" --no-allow-unauthenticated
```

Or delete services:

```bash
gcloud run services delete "$FRONTEND_SERVICE" --region "$REGION"
gcloud run services delete "$BACKEND_SERVICE" --region "$REGION"
```

Optionally delete demo secrets and old images after the week.
