# CognizInterview Graph RAG

A production-minded Graph RAG chatbot that answers questions about uploaded PDFs with citations, ontology graphs, and explainable traces.

Built by Gowtham Ram M for the interview process.

---

## What This Is

This is a working document intelligence system that ingests long PDFs, builds a dynamic knowledge graph, and answers questions with traceable evidence. Every answer links back to specific pages, evidence spans, graph paths, and model reasoning.

The system is designed so that a reviewer can inspect how an answer was produced without reading the code first.

---

## The Architecture At a Glance

```
PDF Upload
    |
    v
LlamaParse Agentic  ----->  Page-level text + tables + layout
    |
    v
Dynamic Ontology Extraction  ----->  Entities, Relationships, Evidence Spans
    |
    v
Cloud SQL (state)  +  Neo4j (graph)  +  GCS (raw PDFs)
    |
    v
User Question  ----->  Router  ----->  Retrieval  ----->  Reranking  ----->  Graph Paths  ----->  Answer Generation
    |
    v
Explainable Trace (every step recorded, scored, and inspectable)
```

---

## How the Pipeline Works

### 1. Document Ingestion

When a PDF is uploaded, the backend runs a multi-stage extraction:

**LlamaParse Agentic** parses the PDF with layout awareness. It understands headers, tables, columns, and page structure. The result is clean, structured markdown per page.

**Ontology Extraction** then scans each page and identifies:
- **Entities** (e.g., "AI RMF", "NIST", "Govern", "Map")
- **Object types** (e.g., Document, Page, EvidenceSpan, Entity, Table)
- **Relationships** (e.g., "Table RELATED_TO Contents", "Page HAS_EVIDENCE EvidenceSpan")
- **Evidence spans** (text chunks with semantic meaning)

This is not a fixed schema. The ontology is extracted dynamically per document. A 48-page NIST AI Risk Management Framework document will produce different entity types and relationships than a 22-page technical project proposal.

**Storage strategy:**
- **Cloud SQL** stores documents, pages, traces, skills, and retrieval state
- **Neo4j** stores the graph of entities and relationships
- **Google Cloud Storage** stores the original PDF and extracted page artifacts
- **Vertex AI** (or Gemini API) stores embeddings for semantic search

### 2. Question Routing

When a user asks a question, the system first decides which "route" to take:

| Route | When it is used | What happens |
|-------|----------------|--------------|
| `greeting` | User says "hello" or "thanks" | Returns a polite greeting, no retrieval |
| `graph_rag` | Normal question about document content | Full pipeline: retrieve, rerank, graph paths, answer |
| `ontology` | "What entities are in the document?" | Returns ontology summary instead of a narrative answer |
| `skill_management` | "What skills are available?" | Returns skill definitions |
| `fallback` / `out_of_scope` | Question is off-topic | Returns a fallback message with best-effort retrieval |

The router is a lightweight OpenAI model call (`gpt-5.4-mini`) with a prompt that includes the question and a few document metadata hints. It runs in ~50ms and determines the rest of the pipeline.

### 3. Retrieval

For `graph_rag` questions, the system retrieves evidence in two stages:

**Stage 1: Hybrid Retrieval**
- **Semantic search**: The question is embedded with Gemini Embedding 2. The system finds pages whose evidence spans have the closest cosine similarity.
- **Lexical (BM25) search**: The question is tokenized and matched against page text using inverted-index keyword search.

These two lists are merged and scored using a weighted combination: `combined_score = 0.7 * semantic_score + 0.3 * lexical_score`.

**Stage 2: Vertex Reranking**

The top ~40 hybrid candidates are sent to Google's Vertex Agent Search Ranking API (`semantic-ranker-default-004`). This re-scores every candidate using a cross-attention model that compares the question directly against the candidate text. The result is a more accurate `final_score`.

The reranked top-8 evidence spans are selected for answer generation.

### 4. Graph Path Expansion

After retrieval, the system queries Neo4j for graph paths that connect the retrieved entities. For example, if the question mentions "AI RMF core functions" and the retriever found a "Govern" entity on page 5, the graph query might discover:

```
Page(5) -> HAS_EVIDENCE -> EvidenceSpan(12) -> MENTIONS -> Entity("Govern")
Entity("Govern") -> RELATED_TO -> Entity("Map")
Entity("Map") -> MENTIONS -> EvidenceSpan(15)
```

These graph paths are returned alongside the answer as additional context. They help the model understand entity relationships that span multiple pages.

### 5. Answer Generation

The answer synthesizer receives:
1. The user's question
2. The top-8 reranked evidence spans (with text, page numbers, scores)
3. The graph paths connecting entities
4. The selected skill format (if any)

It constructs a prompt that grounds the answer in the evidence. The prompt looks like:

```
Answer the user's question using ONLY the provided evidence below.
If the evidence does not contain the answer, say so.

Evidence:
[1] Page 5: "The GOVERN function establishes..."
[2] Page 12: "The MAP function builds..."
...

Graph paths:
Page(5) -> Govern -> Map -> Measure -> Manage

Question: What are the four core functions?
```

The model (`gpt-5.4-mini` or `gpt-5.4`) generates the answer. The system then:
- Extracts citations automatically (the model is instructed to cite evidence numbers)
- Formats the output according to the selected skill (see Skills below)
- Records token usage, latency, and model calls in the trace

### 6. Tracing Every Answer

Every answer produces a `TraceDetail` object with:

| Field | What's in it |
|-------|-------------|
| `user_message` | The original question |
| `answer` | The final generated text |
| `route` | Which route was taken (graph_rag, greeting, etc.) |
| `retrieval` | Full list of evidence candidates with semantic, lexical, rerank, and final scores |
| `evidence` | Evidence spans used in the answer |
| `graph_paths` | Neo4j relationship paths discovered |
| `model_calls` | Each LLM call with model name, tokens, purpose |
| `usage` | Total tokens, cached tokens, estimated latency |
| `timings` | Duration of each pipeline step (retrieval, reranking, generation) |

The frontend `/trace` page visualizes this as a LangSmith-style waterfall timeline:
- Horizontal bars show each pipeline step's duration
- Color-coded by operation type (retrieval = blue, reranking = amber, graph = violet, generation = emerald)
- Click any bar to inspect its input, output, metadata, and errors

---

## Skills: Structured Answer Formats

Skills are JSON templates that tell the answer generator how to format its response. Think of them as prompt-injected style guides.

When a skill is selected, the answer prompt is extended with:
- Required sections (e.g., Executive Summary, Key Findings, Recommendations)
- Word limits per section
- Citation requirements per section
- Tone (executive, technical, audit, concise, cyber)

### Built-in: McKinsey Executive (`mckinsey_executive`)

Upload `mckinsey-skill.json` from the repo root. This skill forces answers into a **Situation-Complication-Resolution (SCR)** structure:

1. **Executive Summary** — 80 words, no citations
2. **Situation & Complication** — 120 words, citations required
3. **Key Findings** — 200 words, citations required
4. **So What?** — 100 words, insight focus
5. **Recommendations** — 150 words, prioritized actions with citations
6. **Implementation & Next Steps** — 120 words, execution roadmap

**How to demo it:**
1. Go to `/chat`
2. Click **Upload JSON skill** and select `mckinsey-skill.json`
3. Ask: *"How should AI systems be made secure and resilient?"*
4. The answer will come back in McKinsey SCR format with footnote-style citations

---

## The Frontend

The frontend is a Next.js 16 app with a premium Material 3 + Liquid Glass design:

| Page | Purpose |
|------|---------|
| `/` | Product walkthrough with animated pipeline visualization |
| `/chat` | Document upload, skill selection, streaming chat with citations |
| `/trace` | LangSmith-style observability: waterfall timeline, retrieval scores, ontology, graph paths |
| `/about` | Interview context and project background |

### Design System
- **Typography**: Google Sans Flex (variable font, crisp at small sizes)
- **Color palette**: Teal/slate (`#0d9488` primary)
- **Animations**: Framer Motion page transitions, staggered message entrances, micro-interactions on buttons
- **Glass surfaces**: Backdrop-filter blur with subtle border highlights

---

## Local Setup

### Prerequisites

- Python 3.13+
- `uv` (Python package manager)
- Node.js 24+
- `pnpm` 10+
- Docker Desktop (for local Postgres + Neo4j)

### Quick Start

**1. Install dependencies**

```bash
# Backend
uv sync --project apps/backend --all-groups

# Frontend
pnpm install
```

**2. Set up environment**

```bash
cp .env.example .env
# Edit .env with your LlamaCloud, OpenAI, Gemini, Neo4j credentials
```

**3. Start local infrastructure**

```bash
docker compose up -d postgres neo4j fake-gcs
```

**4. Run backend**

```bash
cd apps/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**5. Run frontend**

```bash
pnpm --filter @cognizinterview/frontend dev
```

Open:
- Frontend: http://127.0.0.1:3000
- Backend docs: http://127.0.0.1:8000/docs

### Cloud-Backed Local Demo

Instead of local Docker, use Cloud SQL + Neo4j AuraDB:

```bash
# Terminal 1: Cloud SQL proxy
./.bin/cloud-sql-proxy "$CLOUD_SQL_INSTANCE_CONNECTION_NAME" --port 5432

# Terminal 2: Backend
uv run --project apps/backend uvicorn --app-dir apps/backend app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 3: Frontend
pnpm --dir apps/frontend dev
```

---

## Project Structure

```
CognizInterview/
├── apps/
│   ├── backend/           # FastAPI application
│   │   ├── app/
│   │   │   ├── api/       # REST endpoints (chat, docs, ontology, traces, skills)
│   │   │   ├── core/      # Config, auth, tracing middleware
│   │   │   ├── rag/       # Router, answerer, prompts, model policy, usage tracking
│   │   │   └── services/  # Embeddings, parsing, retrieval, reranking, Neo4j, skills
│   │   └── tests/
│   └── frontend/          # Next.js 16 application
│       ├── src/
│       │   ├── app/       # Routes (/, /chat, /trace, /about)
│       │   ├── components/# ChatWorkspace, TraceExplorer, TraceWaterfall, etc.
│       │   └── lib/       # API client, types, streaming helpers
│       └── package.json
├── docs/                  # Backend endpoint tests, deployment guides, roadmap
├── deploy/                # Cloud Run deployment configs
├── infra/                 # Terraform infrastructure
├── mckinsey-skill.json    # Example skill template
└── .env.example           # Environment template
```

---

## Verification

**Backend:**
```bash
uv run --project apps/backend pytest
uv run --project apps/backend ruff check
```

**Frontend:**
```bash
pnpm --dir apps/frontend lint
pnpm --dir apps/frontend test
pnpm --dir apps/frontend build
```

**Smoke tests (with terminals running):**
```bash
# Health
curl http://127.0.0.1:8000/healthz

# Documents list
curl -H "x-api-key: $API_AUTH_KEY" http://127.0.0.1:8000/v1/documents

# Streaming chat
curl --no-buffer \
  -H "x-api-key: $API_AUTH_KEY" \
  -H "Content-Type: application/json" \
  -X POST http://127.0.0.1:8000/v1/chat/stream \
  -d '{"document_id":"YOUR_DOC_ID","message":"What are the four core functions?"}'
```

Expected SSE events: `progress` → `route` → `citation` → `answer_delta` → `metrics` → `trace` → `done`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | Next.js 16, React 19, TypeScript, Tailwind CSS v4, Framer Motion, Lucide icons |
| **Backend** | FastAPI, Python 3.13, Pydantic v2, SQLAlchemy (async), uv |
| **Database** | Cloud SQL (PostgreSQL) for relational state, Neo4j for graph |
| **Parsing** | LlamaParse Agentic (primary), LiteParse (fallback) |
| **Embeddings** | Gemini Embedding 2 (Google AI Studio) |
| **LLM** | OpenAI Responses API (`gpt-5.4-mini` for routing/answer, `gpt-5.4` for complex synthesis) |
| **Reranking** | Vertex AI Agent Search Ranking API (`semantic-ranker-default-004`) |
| **Storage** | Google Cloud Storage (PDFs, artifacts) |
| **Deployment** | Docker, Cloud Run, Terraform |

---

## What Makes This Different

Most RAG demos stop at "upload a PDF and ask questions." This one goes further:

1. **Explainability**: Every answer exposes its full reasoning chain — not just citations, but retrieval scores, reranker diagnostics, graph paths, token usage, and latency.
2. **Dynamic ontology**: It does not rely on a fixed schema. Each document gets its own extracted entity-relationship graph.
3. **Skill-based formatting**: Answers can be shaped into executive briefs, technical deep-dives, audit reports, or any custom format via JSON skills.
4. **Production touches**: API auth, tracing, smoke tests, Cloud SQL + Neo4j persistence, and a deployment pipeline.

---

## Environment

Use only the root `.env`. Both backend and frontend scripts read from this file.

Copy the example:

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

---

## License


