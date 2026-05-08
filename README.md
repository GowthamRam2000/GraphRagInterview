# CognizInterview Graph RAG Chatbot

Upload-first Graph RAG chatbot for long PDF documents. Users upload PDFs, the backend ingests them page-by-page, extracts a dynamic ontology, stores graph/evidence data in Neo4j, and answers questions with citations, graph paths, skills-based formatting, and explainable traces.

## Phase 0 Local Setup

Prerequisites:

- Python 3.13+
- uv
- Node.js 24+
- pnpm 10+
- Docker Desktop or compatible Docker runtime for fully local Postgres/Neo4j, or live GCP/Neo4j credentials for the cloud-backed demo

Install backend dependencies:

```bash
uv sync --project apps/backend --all-groups
```

Install frontend dependencies:

```bash
pnpm install
```

For a local-only sandbox, start local infrastructure:

```bash
docker compose up -d postgres neo4j fake-gcs
```

For the interview/demo path used in this repo, keep data in Cloud SQL/Neo4j and start the Cloud SQL Auth Proxy before Uvicorn:

```bash
./.bin/cloud-sql-proxy "$CLOUD_SQL_INSTANCE_CONNECTION_NAME" --port 5432
```

With that proxy running, `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/DB` writes to Cloud SQL, not to a local Postgres instance. In Cloud Run, do not expose Cloud SQL to end users; attach the Cloud SQL instance to the service and set `DATABASE_URL` to the Unix socket form from `DATABASE_URL_CLOUD_RUN`.

Run backend:

```bash
cd apps/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Or, from the repository root:

```bash
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --host 127.0.0.1 --port 8000 --reload
```

Run frontend:

```bash
pnpm --filter @cognizinterview/frontend dev
```

Open the UI at [http://127.0.0.1:3000](http://127.0.0.1:3000). The backend Swagger docs stay at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Frontend routes:

- `/`: premium product walkthrough for the Graph RAG pipeline.
- `/about`: interview-process context for Gowtham Ram M and Cognizant.
- `/chat`: document upload, document selection, skill selection/upload, streaming chat, citations, and live answer trace.
- `/trace`: trace log, retrieval scores, Vertex rerank diagnostics, ontology summary, graph paths, search preview, and smoke checks.

## Workspace Layout

- Backend app: `apps/backend`
- Backend Python project file: `apps/backend/pyproject.toml`
- Python environment: root `.venv`, managed by `uv`
- Frontend app: `apps/frontend`
- Frontend package: `apps/frontend/package.json`
- JavaScript workspace dependencies: root `node_modules`, managed by `pnpm`
- Shared environment file: root `.env`

Do not create separate `.env` files inside `apps/backend` or `apps/frontend`. The backend loads the root `.env`, and frontend scripts load the same file with `dotenv -e ../../.env`.

## Development Commands

Backend checks:

```bash
uv run --project apps/backend pytest
uv run --project apps/backend ruff check
```

Frontend checks:

```bash
pnpm --filter @cognizinterview/frontend test
pnpm --filter @cognizinterview/frontend lint
pnpm --filter @cognizinterview/frontend build
```

The frontend production build uses `next build --webpack` so it works reliably in local sandboxed and CI-like environments. The frontend dev server uses `next dev --turbopack`.

## Agent And Operator Notes

Use this section when another agent, interviewer, or local operator needs to run the project without rediscovering the layout.

Cloud Run deployment for the one-week demo is documented in [Cloud Run One-Week Demo Deployment](docs/cloud-run-week-demo.md). The deploy path reads root `.env`, stores secrets in Secret Manager, generates Cloud Run env files, deploys backend/frontend, and redeploys backend with exact frontend CORS.

### Important paths

- Repository root: `/Users/gowthamram/PycharmProjects/CognizInterview`
- Root env file: `/Users/gowthamram/PycharmProjects/CognizInterview/.env`
- Backend app: `/Users/gowthamram/PycharmProjects/CognizInterview/apps/backend`
- Backend entrypoint: `apps/backend/app/main.py`
- Backend routes: `apps/backend/app/api`
- Backend RAG layer: `apps/backend/app/rag`
- Backend tests: `apps/backend/tests`
- Frontend app: `/Users/gowthamram/PycharmProjects/CognizInterview/apps/frontend`
- Frontend chat workspace: `apps/frontend/src/components/ChatWorkspace.tsx`
- Frontend API client: `apps/frontend/src/lib/api.ts`
- Frontend tests: `apps/frontend/src/**/*.test.tsx` and `apps/frontend/src/**/*.test.ts`
- Cloud SQL Auth Proxy binary: `.bin/cloud-sql-proxy`
- Demo PDF: `NIST.AI.100-1.pdf`

### Dependency locations

- Python dependencies are managed by `uv` from `apps/backend/pyproject.toml`.
- The Python virtual environment is the root `.venv`.
- JavaScript dependencies are managed by `pnpm`.
- The JavaScript workspace uses the root `node_modules`; do not create a nested `node_modules` manually.
- Backend and frontend both read the root `.env`; do not create separate env files under `apps/backend` or `apps/frontend`.

### Required local terminals

Open three terminals from the repository root for the cloud-backed local demo.

Terminal 1, Cloud SQL Auth Proxy:

```bash
cd /Users/gowthamram/PycharmProjects/CognizInterview
set -a
source .env
set +a
./.bin/cloud-sql-proxy "$CLOUD_SQL_INSTANCE_CONNECTION_NAME" --port 5432
```

Terminal 2, FastAPI backend:

```bash
cd /Users/gowthamram/PycharmProjects/CognizInterview
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 3, Next.js frontend:

```bash
cd /Users/gowthamram/PycharmProjects/CognizInterview
pnpm --dir apps/frontend dev
```

Open:

- Frontend: [http://127.0.0.1:3000](http://127.0.0.1:3000)
- Chat workspace: [http://127.0.0.1:3000/chat](http://127.0.0.1:3000/chat)
- Trace UI: [http://127.0.0.1:3000/trace](http://127.0.0.1:3000/trace)
- Backend docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Auth and endpoint access

All `/v1/*` backend endpoints require the API key from `.env`:

```bash
set -a
source .env
set +a
curl -H "x-api-key: $API_AUTH_KEY" http://127.0.0.1:8000/v1/documents
```

Swagger docs also require the same key. In `/docs`, click **Authorize** and enter the `API_AUTH_KEY` value.

The frontend uses `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_DEMO_API_KEY` from the same root `.env`. For local demo mode, `NEXT_PUBLIC_DEMO_API_KEY` must match `API_AUTH_KEY`.

### Smoke tests

Run these after the three terminals are up:

```bash
curl http://127.0.0.1:8000/healthz
curl -H "x-api-key: $API_AUTH_KEY" http://127.0.0.1:8000/v1/documents
curl -H "x-api-key: $API_AUTH_KEY" http://127.0.0.1:8000/v1/traces/admin/smoke
```

Streaming chat smoke, replacing the document id if needed:

```bash
curl --no-buffer \
  -H "x-api-key: $API_AUTH_KEY" \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/v1/chat/stream \
  -d '{"document_id":"doc_3183e20e5d1245ec","message":"What are the four core functions in the AI Risk Management Framework?"}'
```

Expected stream shape:

```text
event: progress
event: route
event: citation
event: answer_delta
event: metrics
event: trace
event: done
```

### Verification commands

Backend:

```bash
uv run --project apps/backend ruff check
uv run --project apps/backend pytest
```

Frontend:

```bash
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend test
pnpm --dir apps/frontend build
```

### Common gotchas

- If backend startup says port `8000` is in use, another Uvicorn process is already running.
- If frontend startup says port `3000` is in use, another Next.js process is already running.
- If database calls fail locally, check that the Cloud SQL proxy is running on `127.0.0.1:5432`.
- If protected endpoints return `Missing or invalid API key`, use the `x-api-key` header and confirm `NEXT_PUBLIC_DEMO_API_KEY` matches `API_AUTH_KEY`.
- Do not print or commit real `.env` secrets.

## Demo Flow

1. Start the backend and frontend with the commands above.
2. Upload a PDF from the left panel. The current backend uses LlamaParse with `LLAMAPARSE_TIER=agentic` and stores parsed page text, ontology objects, evidence, embeddings, and traces.
3. Select the uploaded document once it appears in the document list.
4. Ask sample questions such as:

```text
What are the core functions of the NIST AI Risk Management Framework?
How should AI systems be made secure and resilient?
What does the MEASURE function ask organizations to do?
```

5. Create the built-in Cyber Brief skill from the Skills panel and ask a risk question with that skill selected. The response should switch into the skill-driven executive/risk/evidence format.
6. Use the Ontology and Traces tabs to explain how the answer was produced: retrieved pages, evidence snippets, graph paths, citations, route decision, token estimates, and admin smoke status.

## Environment

Use only the root `.env`. Both backend and frontend scripts read from this file.

Start by copying:

```bash
cp .env.example .env
```

The env file is a simple key-value file: `KEY=value`.

| Variable | Local value to use | Where to get it |
| --- | --- | --- |
| `APP_ENV` | `local` | Fixed local value. |
| `STORE_BACKEND` | `sql` for the cloud-backed local demo and Cloud Run | Use `memory` only for isolated unit tests or throwaway local work. |
| `GRAPH_STORE_BACKEND` | `neo4j` for the cloud-backed local demo and Cloud Run | Use `memory` only for isolated unit tests or throwaway local work. |
| `API_AUTH_KEY` | Any strong local string, for example `dev-local-auth-key` | You create this. Frontend sends it as `x-api-key` in local/demo mode. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/graphrag` | From local Docker Postgres or Cloud SQL Auth Proxy. In Cloud Run, override this with the Cloud SQL Unix socket URL from Secret Manager. |
| `DATABASE_URL_CLOUD_RUN` | `postgresql+asyncpg://USER:PASSWORD@/DB?host=/cloudsql/PROJECT:REGION:INSTANCE` | Reference value for Cloud Run deployment; the app reads `DATABASE_URL`. |
| `NEO4J_URI` | `bolt://localhost:7687` | From local `docker-compose.yml` Neo4j. In cloud, get it from Neo4j AuraDB connection details. |
| `NEO4J_USERNAME` | `neo4j` | From local `docker-compose.yml` Neo4j or Neo4j AuraDB user. |
| `NEO4J_PASSWORD` | `password` | From local `docker-compose.yml` Neo4j or Neo4j AuraDB password. |
| `GCS_BUCKET_RAW` | `raw-pdfs` | Local fake GCS bucket name. In cloud, create this in GCS. |
| `GCS_BUCKET_ARTIFACTS` | `page-artifacts` | Local fake GCS bucket name. In cloud, create this in GCS. |
| `GCP_PROJECT_ID` | Empty locally unless using live GCP | Get from Google Cloud Console project selector. |
| `GCP_REGION` | `us-central1` | Choose the GCP region for Cloud Run, Vertex AI, and storage. |
| `PARSER_PRIMARY` | `llamaparse` | Fixed app setting. |
| `PARSER_FALLBACK` | `liteparse` | Fixed app setting. |
| `LLAMA_CLOUD_API_KEY` | Your LlamaCloud key | Get from LlamaCloud / LlamaIndex Cloud account API keys. |
| `LLAMAPARSE_TIER` | `agentic` | LlamaParse tier. Agentic is the default for layout-aware parsing. |
| `LLAMAPARSE_RESULT_TYPE` | `markdown` | Fixed app setting for readable extraction output. |
| `LITEPARSE_OCR_ENABLED` | `false` | Set `true` if using LiteParse OCR fallback locally. |
| `LITEPARSE_DPI` | `150` | Fixed local default; increase for scanned PDFs if needed. |
| `OPENAI_API_KEY` | Your OpenAI API key | Get from OpenAI Platform API keys. |
| `GEMINI_API_KEY` | Your Gemini API key | Get from Google AI Studio. Used for Gemini embeddings. |
| `ROUTER_MODEL` | `gpt-5.4-mini` | OpenAI model name. |
| `EXTRACTOR_MODEL` | `gpt-5.4-mini` | OpenAI model name. |
| `ANSWER_MODEL` | `gpt-5.4-mini` | OpenAI model name. |
| `GREETING_MODEL` | `gpt-5.4-mini` | OpenAI model name. |
| `LLM_ANSWER_ENABLED` | `true` | Use OpenAI Responses API for answer synthesis after retrieval; falls back to extractive answers on errors. |
| `ROUTER_REASONING_EFFORT` | `none` | No-thinking deterministic/mini-model routing policy. |
| `ANSWER_REASONING_EFFORT` | `low` | Thinking budget for grounded answer synthesis. |
| `EXTRACTOR_REASONING_EFFORT` | `low` | Thinking budget documented for ontology extraction prompts. |
| `PROMPT_CACHE_NAMESPACE` | `cognizinterview-graphrag-v1` | Stable namespace used to create OpenAI `prompt_cache_key` values. |
| `ANSWER_MAX_OUTPUT_TOKENS` | `900` | Max answer tokens for the OpenAI answer call. |
| `EMBEDDING_PROVIDER` | `gemini_api` | Use Gemini Developer API key auth for embeddings. |
| `EMBEDDING_MODEL` | `gemini-embedding-2` | Gemini embedding model id. Smoke tested with your Gemini API key. |
| `EMBEDDING_DIMENSION` | `1536` | Output dimensionality for Gemini embeddings. |
| `EMBEDDING_TASK_TYPE` | `RETRIEVAL_DOCUMENT` | Gemini embedding task type for document/page/entity vectors. |
| `RERANK_PROVIDER` | `vertex` | Use Google Agent Search / Discovery Engine Ranking API after local hybrid retrieval. |
| `RERANK_MODEL` | `semantic-ranker-default-004` | Vertex ranking model for semantic reranking. |
| `RERANK_LOCATION` | `global` | Ranking API location. |
| `RERANK_TOP_N` | `8` | Number of reranked records requested from Vertex. |
| `RERANK_CANDIDATE_LIMIT` | `40` | Number of hybrid semantic/BM25 candidates sent to reranking. |
| `NEXT_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Local backend URL. |
| `NEXT_PUBLIC_DEMO_API_KEY` | Same value as `API_AUTH_KEY` | You create this; it is public in browser builds, so use demo/local keys only. |

Do not commit real `.env` values. Only `.env.example` is checked in.

For full GCP setup, Cloud SQL values, Secret Manager values, IAM roles, and deployment env mapping, see [GCP Env And Deployment Setup](docs/roadmap/gcp-env-and-deployment-setup.md).

For a local demo that writes to Cloud SQL, start the Cloud SQL Auth Proxy before Uvicorn:

```bash
./.bin/cloud-sql-proxy PROJECT:REGION:INSTANCE --port 5432
```

Then keep `STORE_BACKEND=sql`, `GRAPH_STORE_BACKEND=neo4j`, and `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/DB`. On Cloud Run, set `DATABASE_URL` to the Unix socket URL and attach the Cloud SQL instance to the service.

## Parser Strategy

Phase 1 uses this parser order:

1. LlamaParse through the active `llama-cloud` Python package when `LLAMA_CLOUD_API_KEY` is configured.
2. LiteParse fallback through the `liteparse` Python package and `@llamaindex/liteparse` Node CLI when LlamaParse is unavailable.
3. PyMuPDF/pdfplumber only as a low-level local extraction utility, not the primary parser path.

The parser env values are:

```env
PARSER_PRIMARY=llamaparse
PARSER_FALLBACK=liteparse
LLAMA_CLOUD_API_KEY=
LLAMAPARSE_TIER=agentic
LLAMAPARSE_RESULT_TYPE=markdown
LITEPARSE_OCR_ENABLED=false
LITEPARSE_DPI=150
```

Use `API_AUTH_KEY=dev-local-auth-key` for local secured endpoint tests starting in Phase 1.

## Backend RAG Layer

Backend RAG code lives under `apps/backend/app/rag`:

- `prompts.py`: versioned router, extractor, and answer prompt templates with evidence boundaries.
- `model_policy.py`: `gpt-5.4-mini` routing/answer/extractor profiles and thinking vs no-thinking settings.
- `answerer.py`: OpenAI Responses API answer synthesis with `prompt_cache_key`, fallback behavior, and model-call trace metadata.
- `usage.py`: token usage, cached-token extraction, estimates, and latency helpers.

Every Graph RAG trace now includes sanitized `prompts`, `model_calls`, `usage`, `timings`, and `cache` fields in addition to retrieval scores, evidence, graph paths, and citations.
