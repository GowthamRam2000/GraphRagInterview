# Graph RAG Chatbot Delivery Plan

## Phase 0: Environment And Skeleton

- Create monorepo structure for backend, frontend, docs, and infra.
- Install current backend and frontend dependency sets.
- Add local Docker Compose for Postgres, Neo4j, and fake GCS.
- Install LlamaParse/LlamaCloud and LiteParse parser dependencies.
- Add environment templates and local setup documentation.
- Add minimal FastAPI and Next.js shells that compile and run.

Exit criteria:

- `uv sync --project apps/backend --all-groups` succeeds.
- `uv run --project apps/backend pytest` succeeds.
- `pnpm install` succeeds.
- `pnpm --filter @cognizinterview/frontend lint` succeeds.
- `pnpm --filter @cognizinterview/frontend build` succeeds.

## Phase 1: Complete Secured Backend

- Implement API-key auth on all `/v1/*` endpoints, leaving `/healthz` public.
- Implement document upload-url, finalize, ingestion status, ontology, skills, chat stream, and trace APIs.
- Implement page-wise PDF validation, LlamaParse primary parser, LiteParse fallback parser, Gemini API embedding adapter, OpenAI structured extraction adapter, Neo4j graph writer, and LangGraph workflow.
- Persist tenants, documents, ingestion runs, page statuses, skills, conversations, traces, and LangGraph checkpoints in Postgres.
- Store graph objects, entities, relationships, evidence, page vectors, and entity vectors in Neo4j.
- Add unit and integration tests for auth, routing, ingestion idempotency, skill safety, Graph RAG citations, and trace redaction.

Exit criteria:

- All backend endpoints are tested with valid and invalid auth keys.
- Ingestion never sends a whole document to an LLM.
- A fixture PDF produces ontology objects, evidence, citations, and trace records.

## Phase 2: Frontend Connected To Backend

- Build the operational workbench UI: upload, ingestion progress, chat, evidence, graph paths, ontology, skills, and admin trace views.
- Connect every view to the backend API with typed clients and loading/error states.
- Add admin trace view showing route, retrieved data, graph paths, citations, model calls, token usage, and timings.
- Add ontology explorer showing domain object types, properties, links, counts, and evidence.
- Add skill uploader and preview flow.

Exit criteria:

- A user can upload a PDF, watch ingestion, ask a question, see the cited answer, open the trace, and inspect the ontology.
- Frontend lint, build, and component tests pass.

## Phase 3: End-To-End Evaluation And Demo Hardening

- Add 30+ golden test questions across greetings, ontology, extraction, factual lookup, relationship explanation, and skill formatting.
- Add synthetic 30-page fixture PDF for repeatable local demos.
- Add trace export and seeded demo scenarios.
- Tune retrieval, citation coverage, and answer validation.
- Add failure-mode demos for unsafe skills, missing evidence, failed pages, and reprocessing.

Exit criteria:

- Route accuracy is at least 95 percent on the golden set.
- Citation coverage is at least 90 percent.
- Unsupported factual claims are zero on critical golden questions.

## Phase 4: Cloud Deployment

- Provision GCP services with Terraform.
- Deploy backend, frontend, worker, and Cloud Run jobs.
- Configure Cloud SQL, GCS, Cloud Tasks, Secret Manager, Cloud Logging, Cloud Trace, Gemini API embeddings, LlamaParse, LiteParse fallback, and Neo4j AuraDB.
- Add CI/CD build and deploy commands.
- Run smoke tests against the cloud URL.

Exit criteria:

- Public demo URL works behind auth.
- Upload, ingestion, chat, ontology, skills, and trace views work in cloud.
- Logs and traces are sanitized and visible for demo explanation.
