# GCP Env And Deployment Setup

Use only the root `.env`. For local development, copy `.env.example` to `.env`. For Cloud Run deployment, put secret values in Secret Manager and non-secret values directly on the Cloud Run service.

## Important Rule

There is no general `GCP_API_KEY` for this app.

GCP services in this project should use:

- Local development: Application Default Credentials from `gcloud auth application-default login`, or a service-account JSON path in `GOOGLE_APPLICATION_CREDENTIALS`.
- Cloud Run: the Cloud Run service account attached to the service.
- Secrets: Secret Manager mounted/injected into Cloud Run.

Do not put GCP service-account JSON content into `.env`.

## What To Create In GCP

Create or configure these resources before deployment:

| Resource | What to create | Where to get the value |
| --- | --- | --- |
| GCP project | One project, billing enabled | Google Cloud Console project selector. Use project ID for `GCP_PROJECT_ID`. |
| Service accounts | `graph-rag-api-sa`, `graph-rag-worker-sa`, `graph-rag-deploy-sa` | IAM & Admin > Service Accounts. Use these on Cloud Run/jobs, not as API keys. |
| Cloud SQL Postgres | Instance, database `graphrag`, user `graphrag_app` | Cloud SQL instance overview gives `CLOUD_SQL_INSTANCE_CONNECTION_NAME`; database/user/password become DB env/secret values. |
| Neo4j AuraDB | AuraDB instance | Neo4j Aura console gives `NEO4J_URI`, username, and password. |
| GCS buckets | Raw PDF bucket and artifact bucket | Cloud Storage bucket names become `GCS_BUCKET_RAW` and `GCS_BUCKET_ARTIFACTS`. |
| Gemini API | Gemini API key | Google AI Studio gives `GEMINI_API_KEY`; used for embeddings. |
| LlamaCloud | LlamaParse API key | LlamaCloud API keys page gives `LLAMA_CLOUD_API_KEY`. |
| OpenAI | OpenAI API key | OpenAI Platform API keys page gives `OPENAI_API_KEY`. |
| Secret Manager | Secrets for API keys/passwords | Secret names are referenced by Cloud Run env injection. |
| Artifact Registry | Docker image repository | Terraform/Cloud Build uses it for backend/frontend/worker images. |
| Cloud Run | Backend API, frontend, worker, jobs | Uses service accounts and Secret Manager values. |
| Cloud Tasks | Page ingestion queue | Used by backend to enqueue page-by-page work. |

## GCP APIs To Enable

Enable:

```bash
gcloud services enable run.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable storage.googleapis.com
gcloud services enable cloudtasks.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable cloudtrace.googleapis.com
```

## Local `.env` Values

Use these values for local development:

```env
APP_ENV=local
STORE_BACKEND=memory
GRAPH_STORE_BACKEND=memory
API_AUTH_KEY=dev-local-auth-key
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/graphrag
DB_NAME=graphrag
DB_USER=graphrag_app
DB_PASSWORD=
CLOUD_SQL_INSTANCE_CONNECTION_NAME=
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
GCS_BUCKET_RAW=raw-pdfs
GCS_BUCKET_ARTIFACTS=page-artifacts
GCP_PROJECT_ID=
GCP_REGION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=
PARSER_PRIMARY=llamaparse
PARSER_FALLBACK=liteparse
LLAMA_CLOUD_API_KEY=get-from-llamacloud
LLAMAPARSE_TIER=agentic
LLAMAPARSE_RESULT_TYPE=markdown
LITEPARSE_OCR_ENABLED=false
LITEPARSE_DPI=150
OPENAI_API_KEY=get-from-openai-platform
GEMINI_API_KEY=get-from-google-ai-studio
ROUTER_MODEL=gpt-5.4-mini
EXTRACTOR_MODEL=gpt-5.4-mini
ANSWER_MODEL=gpt-5.4-mini
GREETING_MODEL=gpt-5.4-mini
EMBEDDING_PROVIDER=gemini_api
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=1536
EMBEDDING_TASK_TYPE=RETRIEVAL_DOCUMENT
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_API_KEY=dev-local-auth-key
```

## Cloud Run Env Values

For Cloud Run, use:

```env
APP_ENV=production
STORE_BACKEND=sql
GRAPH_STORE_BACKEND=neo4j
API_AUTH_KEY=secret-manager:api-auth-key
DATABASE_URL=secret-manager:database-url
DB_NAME=graphrag
DB_USER=graphrag_app
DB_PASSWORD=secret-manager:db-password
CLOUD_SQL_INSTANCE_CONNECTION_NAME=project-id:us-central1:graph-rag-postgres
NEO4J_URI=secret-manager:neo4j-uri
NEO4J_USERNAME=secret-manager:neo4j-username
NEO4J_PASSWORD=secret-manager:neo4j-password
GCS_BUCKET_RAW=project-id-graph-rag-raw-pdfs
GCS_BUCKET_ARTIFACTS=project-id-graph-rag-page-artifacts
GCP_PROJECT_ID=project-id
GCP_REGION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=
PARSER_PRIMARY=llamaparse
PARSER_FALLBACK=liteparse
LLAMA_CLOUD_API_KEY=secret-manager:llama-cloud-api-key
LLAMAPARSE_TIER=agentic
LLAMAPARSE_RESULT_TYPE=markdown
LITEPARSE_OCR_ENABLED=false
LITEPARSE_DPI=150
OPENAI_API_KEY=secret-manager:openai-api-key
GEMINI_API_KEY=secret-manager:gemini-api-key
ROUTER_MODEL=gpt-5.4-mini
EXTRACTOR_MODEL=gpt-5.4-mini
ANSWER_MODEL=gpt-5.4-mini
GREETING_MODEL=gpt-5.4-mini
EMBEDDING_PROVIDER=gemini_api
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSION=1536
EMBEDDING_TASK_TYPE=RETRIEVAL_DOCUMENT
NEXT_PUBLIC_API_BASE_URL=https://api-cloud-run-url
NEXT_PUBLIC_DEMO_API_KEY=do-not-use-for-real-production-users
```

`secret-manager:name` means: store the value in Secret Manager, then configure Cloud Run to inject that secret as the env variable. Do not literally set the env value to `secret-manager:name`.

## Database Setup

For local:

- Use Docker Compose Postgres.
- Keep `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/graphrag`.

For GCP:

1. Create Cloud SQL for PostgreSQL.
2. Create database `graphrag`.
3. Create user `graphrag_app`.
4. Generate a strong password and store it in Secret Manager as `db-password`.
5. Copy the instance connection name from Cloud SQL Overview. It looks like:

```text
project-id:us-central1:graph-rag-postgres
```

6. Use one of these deployment connection strategies:

Private IP option:

```env
DATABASE_URL=postgresql+asyncpg://graphrag_app:DB_PASSWORD@PRIVATE_IP:5432/graphrag
```

Cloud SQL socket option:

```env
DATABASE_URL=postgresql+asyncpg://graphrag_app:DB_PASSWORD@/graphrag?host=/cloudsql/project-id:us-central1:graph-rag-postgres
```

For Cloud Run, prefer Secret Manager for the full `DATABASE_URL` so the password is not visible in Terraform state or shell history.

## IAM Roles

Grant `graph-rag-api-sa`:

- `roles/cloudsql.client`
- `roles/storage.objectAdmin` on the app buckets
- `roles/secretmanager.secretAccessor`
- `roles/cloudtasks.enqueuer`
- `roles/logging.logWriter`
- `roles/cloudtrace.agent`

Grant `graph-rag-worker-sa`:

- `roles/cloudsql.client`
- `roles/storage.objectAdmin` on the app buckets
- `roles/secretmanager.secretAccessor`
- `roles/logging.logWriter`
- `roles/cloudtrace.agent`

Grant `graph-rag-deploy-sa`:

- Cloud Run deploy permissions
- Artifact Registry writer
- Service Account User on runtime service accounts
- Terraform-managed resource permissions for deployment

## Secret Manager Values To Create

Create these secrets:

```bash
api-auth-key
openai-api-key
llama-cloud-api-key
gemini-api-key
database-url
db-password
neo4j-uri
neo4j-username
neo4j-password
```

Example:

```bash
printf '%s' 'your-openai-key' | gcloud secrets create openai-api-key --data-file=-
```

## Where Each Key Comes From

| Env key | Get it from |
| --- | --- |
| `API_AUTH_KEY` | You create a strong random value. |
| `OPENAI_API_KEY` | OpenAI Platform > API keys. |
| `GEMINI_API_KEY` | Google AI Studio > API keys. |
| `LLAMA_CLOUD_API_KEY` | LlamaCloud / LlamaIndex Cloud > API keys. |
| `NEO4J_URI` | Neo4j AuraDB instance connection details. |
| `NEO4J_USERNAME` | Neo4j AuraDB connection details. |
| `NEO4J_PASSWORD` | Neo4j AuraDB generated password or reset password. |
| `DATABASE_URL` | Build from Cloud SQL database/user/password/host, then store in Secret Manager. |
| `DB_PASSWORD` | Password created for Cloud SQL user `graphrag_app`. |
| `CLOUD_SQL_INSTANCE_CONNECTION_NAME` | Cloud SQL Overview page or `gcloud sql instances describe`. |
| `GCP_PROJECT_ID` | Google Cloud project selector. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Local only, path to service-account JSON if not using `gcloud auth application-default login`. Leave empty in Cloud Run. |
