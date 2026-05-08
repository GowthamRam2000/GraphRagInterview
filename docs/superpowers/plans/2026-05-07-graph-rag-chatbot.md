# Graph RAG Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a demo-ready Graph RAG chatbot over a 67-page FDA AI-enabled medical device software guidance PDF, with page-wise ingestion, ontology extraction, LLM routing, uploadable output-formatting skills, traceability, logging, and a polished web UI.

**Architecture:** The system uses FastAPI + Pydantic as the backend API, LangGraph as the query workflow orchestrator, Neo4j AuraDB on Google Cloud as the property graph and vector store, Google Cloud Storage for PDF/page artifacts, Vertex AI `multimodalembedding@001` for page image plus short caption embeddings, and OpenAI `gpt-5.4-mini` for routing, extraction, and grounded answer generation. The frontend is a Next.js app with a chat workspace, document ingestion monitor, ontology explorer, skill manager, and trace viewer.

**Tech Stack:** Python 3.14, FastAPI, Pydantic v2, LangGraph, Neo4j GraphRAG Python, Vertex AI multimodal embeddings, OpenAI Responses API, Next.js/React/TypeScript, Tailwind CSS, Cloud Run, Cloud Run Jobs, Pub/Sub, Cloud Tasks, Cloud SQL Postgres, Google Cloud Storage, Secret Manager, Cloud Logging, Cloud Trace, Terraform.

---

## Source Document

Use this public healthcare/regulatory PDF:

- **Document:** FDA, "Artificial Intelligence-Enabled Device Software Functions: Lifecycle Management and Marketing Submission Recommendations"
- **Industry:** Healthcare / medical device regulation
- **Status:** Draft guidance, January 7, 2025
- **Pages:** 67
- **PDF URL:** https://www.fda.gov/media/184856/download
- **FDA landing page:** https://www.fda.gov/regulatory-information/search-fda-guidance-documents/artificial-intelligence-enabled-device-software-functions-lifecycle-management-and-marketing

This document is a strong Graph RAG demo candidate because it naturally contains entities, regulated artifacts, lifecycle phases, documentation requirements, risk concepts, validation concepts, monitoring concepts, labeling concepts, and relationships between them.

## Current Product Facts Used In The Design

- Google Vertex AI multimodal embeddings support `multimodalembedding@001`; the model returns vectors up to 1408 dimensions and accepts text, image, and video inputs. The text input is limited to about 32 tokens, so this plan uses rendered page images plus short retrieval captions for embeddings and stores full page text separately for evidence and answer synthesis.
- OpenAI currently lists `gpt-5.4-mini` as a lower-latency, lower-cost GPT-5.4 variant. The app keeps the model name configurable through environment variables.
- LangGraph models workflows as state, nodes, and edges, which fits the explicit router-to-Graph-RAG flow.
- Cloud Run is used for managed containers and HTTPS services; Cloud Logging and Cloud Trace are used for demo-visible operational telemetry.

## Target Capabilities

1. Upload and ingest a PDF without sending the entire document to an LLM in one request.
2. Process pages one at a time by default, with an optional 3-page window for table continuations.
3. Extract a knowledge graph from the document with typed nodes, typed relationships, evidence spans, page numbers, confidence scores, prompt versions, and model versions.
4. Show all ontology/domain objects, their properties, and their links.
5. Route greetings to a lightweight direct response path and all document questions to the Graph RAG path.
6. Answer with citations, graph paths, retrieved evidence, and trace events.
7. Let users upload safe "skills" that control output formatting without allowing arbitrary code execution or prompt override.
8. Provide a demo UI that makes the architecture explainable: chat, graph explorer, page viewer, trace viewer, ingestion progress, and skill manager.

## Domain Ontology For The Chosen PDF

Initial ontology seed. The ingestion pipeline can add properties and discovered relationships, but these types give the extractor a stable schema.

### Core Nodes

- `GuidanceDocument`: `document_id`, `title`, `issuer`, `status`, `issue_date`, `docket_number`, `source_url`, `page_count`
- `GuidanceSection`: `section_id`, `title`, `section_number`, `start_page`, `end_page`
- `Recommendation`: `recommendation_id`, `text`, `strength`, `topic`, `page_number`, `confidence`
- `RegulatoryPathway`: `name`, `description`, `authority`, `submission_type`
- `MarketingSubmission`: `submission_type`, `name`, `description`
- `DocumentationArtifact`: `artifact_type`, `name`, `purpose`, `required_context`
- `AIEnabledDevice`: `name`, `intended_use`, `device_context`, `risk_profile`
- `DeviceSoftwareFunction`: `name`, `intended_purpose`, `device_definition_basis`
- `AIDeviceSoftwareFunction`: `name`, `model_dependency`, `input_data_type`, `output_type`
- `AIModel`: `model_type`, `architecture`, `training_method`, `input_features`, `output`, `version`
- `Dataset`: `dataset_type`, `source`, `population`, `collection_method`, `representativeness_notes`
- `DataManagementPractice`: `practice_type`, `description`, `quality_control_method`
- `ValidationStudy`: `study_type`, `objective`, `design`, `acceptance_criteria`
- `PerformanceMetric`: `metric_name`, `definition`, `threshold`, `subgroup_applicability`
- `Risk`: `risk_type`, `hazard`, `harm`, `severity`, `probability`
- `RiskControl`: `control_type`, `mitigation`, `verification_method`
- `BiasConcern`: `affected_group`, `bias_type`, `impact`, `detection_method`
- `TransparencyRequirement`: `audience`, `information_need`, `format`, `timing`
- `UserInterfaceElement`: `element_type`, `user_group`, `purpose`, `labeling_dependency`
- `LabelingContent`: `audience`, `content_type`, `claim`, `limitation`
- `MonitoringPlan`: `monitoring_scope`, `metric`, `frequency`, `trigger`, `corrective_action`
- `CybersecurityControl`: `control_name`, `threat`, `mitigation`, `evidence`
- `QualitySystemActivity`: `activity_name`, `process_area`, `documentation`
- `ModelCard`: `model_name`, `intended_use`, `performance_summary`, `limitations`
- `PopulationSubgroup`: `subgroup_type`, `definition`, `relevance`
- `ConsensusStandard`: `standard_name`, `issuing_body`, `topic`, `recognized_status`
- `EvidenceSpan`: `page_number`, `text`, `bbox`, `source_hash`, `extraction_run_id`

### Relationships

- `GuidanceDocument HAS_SECTION GuidanceSection`
- `GuidanceSection CONTAINS_RECOMMENDATION Recommendation`
- `Recommendation APPLIES_TO AIDeviceSoftwareFunction`
- `Recommendation REQUESTS_DOCUMENTATION DocumentationArtifact`
- `MarketingSubmission INCLUDES DocumentationArtifact`
- `AIEnabledDevice HAS_FUNCTION DeviceSoftwareFunction`
- `DeviceSoftwareFunction IMPLEMENTS AIDeviceSoftwareFunction`
- `AIDeviceSoftwareFunction USES_MODEL AIModel`
- `AIModel TRAINED_ON Dataset`
- `AIModel VALIDATED_BY ValidationStudy`
- `ValidationStudy MEASURES PerformanceMetric`
- `Dataset HAS_SUBGROUP PopulationSubgroup`
- `Risk MITIGATED_BY RiskControl`
- `BiasConcern AFFECTS PopulationSubgroup`
- `TransparencyRequirement INFORMED_BY LabelingContent`
- `UserInterfaceElement PRESENTS LabelingContent`
- `MonitoringPlan TRACKS PerformanceMetric`
- `MonitoringPlan DETECTS Risk`
- `CybersecurityControl MITIGATES Risk`
- `QualitySystemActivity PRODUCES DocumentationArtifact`
- `ModelCard SUMMARIZES AIModel`
- `Recommendation SUPPORTED_BY EvidenceSpan`
- `DocumentationArtifact SUPPORTED_BY EvidenceSpan`
- `Risk SUPPORTED_BY EvidenceSpan`

## Repository Structure

```text
apps/
  backend/
    pyproject.toml
    app/
      main.py
      api/
        routes_chat.py
        routes_documents.py
        routes_ontology.py
        routes_skills.py
        routes_traces.py
      core/
        config.py
        logging.py
        security.py
        tracing.py
      models/
        chat.py
        document.py
        graph.py
        ingestion.py
        skill.py
        trace.py
      services/
        gcs_store.py
        vertex_embeddings.py
        openai_llm.py
        neo4j_graph.py
        skill_registry.py
        trace_store.py
      ingestion/
        pdf_pages.py
        page_renderer.py
        page_extractor.py
        graph_normalizer.py
        graph_writer.py
        ingestion_job.py
      rag/
        graph_state.py
        router.py
        retrievers.py
        evidence_packer.py
        answerer.py
        graph_workflow.py
      tests/
        unit/
        integration/
  frontend/
    package.json
    next.config.ts
    src/
      app/
        page.tsx
        documents/page.tsx
        ontology/page.tsx
        skills/page.tsx
        traces/page.tsx
      components/
        chat/
        documents/
        ontology/
        skills/
        traces/
      lib/
        api.ts
        types.ts
infra/
  terraform/
    main.tf
    variables.tf
    cloud_run.tf
    storage.tf
    sql.tf
    secrets.tf
    logging.tf
docs/
  architecture/
    graph-rag-demo.md
  demo/
    script.md
```

## Backend API Contract

### Chat

- `POST /api/chat`
- Request:

```json
{
  "conversation_id": "conv_123",
  "document_id": "fda_ai_dsf_2025",
  "message": "What should be included for performance validation?",
  "skill_id": "executive_brief_v1",
  "demo_trace": true
}
```

- Response:

```json
{
  "answer": "Grounded answer with citations.",
  "route": "graph_rag",
  "citations": [
    {
      "page_number": 27,
      "section_title": "Performance Validation",
      "evidence_id": "ev_abc"
    }
  ],
  "graph_paths": [
    ["ValidationStudy", "MEASURES", "PerformanceMetric"]
  ],
  "trace_id": "trace_123"
}
```

### Documents

- `POST /api/documents` uploads PDF metadata and a signed GCS upload URL.
- `POST /api/documents/{document_id}/ingest` starts page-wise ingestion.
- `GET /api/documents/{document_id}/ingestion-runs/{run_id}` returns progress by page.
- `GET /api/documents/{document_id}/pages/{page_number}` returns text, image URL, graph entities, and extraction confidence.

### Ontology

- `GET /api/documents/{document_id}/ontology` returns node labels, relationship types, properties, counts, and examples.
- `GET /api/documents/{document_id}/ontology/neighborhood?node_id=...` returns graph neighborhood for the explorer.

### Skills

- `POST /api/skills` uploads a safe YAML or JSON skill definition.
- `GET /api/skills` lists validated skills.
- `POST /api/skills/{skill_id}/preview` formats a sample answer through the skill and validates the output contract.

### Traces

- `GET /api/traces/{trace_id}` returns route decision, retrieval inputs, retrieved nodes, graph paths, evidence package, model calls, token usage, latency, and final citations.

## Skill Format

Skills are formatting contracts, not executable plugins. They must not be allowed to call tools, modify retrieval, override system prompts, or execute code.

```yaml
name: executive_brief
version: "1.0.0"
description: "Formats grounded answers for executive stakeholders."
allowed_output_modes:
  - markdown
required_sections:
  - heading: "Decision"
    max_words: 60
  - heading: "Evidence"
    citation_required: true
  - heading: "Risks"
    citation_required: true
style:
  tone: "concise"
  bullets_max: 5
constraints:
  require_page_citations: true
  forbid_uncited_claims: true
```

Skill safety rules:

- Accept only YAML or JSON.
- Validate with Pydantic models.
- Reject keys outside the schema.
- Reject strings containing prompt-control phrases such as "ignore previous instructions", "system prompt", "developer message", "tool call", "exfiltrate", or "secret".
- Limit size to 20 KB.
- Store a SHA-256 hash and immutable version.
- Treat skill text as untrusted data in prompts.
- Validate the generated answer against the skill contract before returning it.
- If validation fails twice, return a safe default answer format with citations.

## LangGraph Query Workflow

State fields:

```python
class GraphRagState(TypedDict):
    conversation_id: str
    document_id: str
    user_message: str
    selected_skill_id: str | None
    route: Literal["greeting", "graph_rag", "ontology", "skill_management", "out_of_scope"]
    normalized_query: str
    retrieval_caption: str
    candidate_entities: list[dict]
    vector_hits: list[dict]
    graph_paths: list[dict]
    evidence_package: list[dict]
    answer: str
    citations: list[dict]
    trace_id: str
```

Nodes:

1. `sanitize_input`
2. `load_skill`
3. `route_query`
4. `greeting_answer`
5. `query_rewrite`
6. `entity_retrieval`
7. `page_vector_retrieval`
8. `graph_expansion`
9. `evidence_packing`
10. `grounded_answer`
11. `skill_format_validation`
12. `persist_trace`

Routing:

- If the message is a greeting or small talk with no document intent, return `greeting_answer`.
- If the message asks for object types, relationships, properties, or schema, use `ontology`.
- If the message uploads, lists, previews, or selects a skill, use `skill_management`.
- Otherwise use `graph_rag`.

## Retrieval Strategy

Because `multimodalembedding@001` is not suitable for long text chunks, retrieval uses three complementary signals:

1. **Page image vector retrieval:** render each PDF page to PNG, generate a 1408-dimension embedding from the image plus a short page caption, and retrieve visually/semantically related pages.
2. **Graph entity retrieval:** extract canonical entities from the question, match them against Neo4j nodes by exact alias, normalized lexical match, and embedding of short node descriptions.
3. **Graph neighborhood expansion:** expand from matched entities to recommendations, documentation artifacts, evidence spans, and section nodes. Rank by path type, confidence, page proximity, and evidence density.

The answerer receives only the packed evidence, never the whole PDF.

## Page-Wise Ingestion Strategy

Default behavior:

- One PDF page is one `PageWorkUnit`.
- The extractor receives page text, page image URL, section context, previous page summary, and next page heading when available.
- The extractor never receives the entire PDF.

Optional behavior:

- If a page contains a table continuation marker, process a 3-page window: previous page, current page, next page.
- The window still emits evidence tied to individual pages.

Idempotency:

- `document_id + page_number + extractor_version + source_hash` uniquely identifies a page extraction.
- Re-ingesting a page replaces only nodes and evidence from the same extraction run unless a human-approved canonical entity already exists.

## Traceability Model

Every chat and ingestion run records:

- `trace_id`
- `conversation_id`
- `document_id`
- route decision and classifier confidence
- model name, reasoning effort, prompt version, and token usage
- embedding model, vector dimension, and embedding input hash
- retrieved vector hits
- matched graph nodes
- Cypher queries
- graph paths used
- final evidence package
- final answer
- citation coverage score
- latency by stage
- errors and retries

Trace storage:

- App trace metadata in Cloud SQL Postgres.
- Operational logs in Cloud Logging.
- Request spans in Cloud Trace.
- Optional analytics export to BigQuery for demo dashboards.

## Frontend Experience

### First Screen

The first screen is the working chat product, not a marketing page.

Layout:

- Left rail: document selector, skill selector, demo scenario selector.
- Center: chat with streaming answer, citations, and follow-up chips.
- Right panel tabs: Evidence, Graph Paths, Trace, Page Preview.

### Documents View

- Upload PDF.
- Show ingestion status by page.
- Display page thumbnails and extraction status.
- Allow "reprocess page" for demo.
- Show failed pages with exact validation errors.

### Ontology View

- Node label summary with counts.
- Relationship type summary with counts.
- Searchable domain object table.
- Graph explorer with page-backed evidence.
- "Explain this object" action that opens a grounded chat query.

### Skills View

- Upload YAML/JSON skill.
- Validation result with rejected keys and safety issues.
- Preview skill formatting against a canned answer.
- Enable/disable skill.

### Traces View

- Timeline of LangGraph nodes.
- Route badge: greeting, graph_rag, ontology, skill_management, out_of_scope.
- Retrieved page hits.
- Cypher queries.
- Evidence package.
- Token and latency metrics.
- Download trace JSON.

## Demo Script

Use these demo questions:

1. "Hi, what can you do?"
   - Expected route: `greeting`
   - Expected behavior: no graph retrieval.
2. "List the domain objects you found in the FDA guidance and show how they connect."
   - Expected route: `ontology`
   - Expected behavior: ontology table plus relationship graph.
3. "What documentation does FDA recommend for AI-enabled device performance validation?"
   - Expected route: `graph_rag`
   - Expected behavior: citations from validation and appendix sections.
4. "Explain the relationship between bias, data management, and performance monitoring."
   - Expected route: `graph_rag`
   - Expected behavior: graph paths linking `BiasConcern`, `Dataset`, `PopulationSubgroup`, `MonitoringPlan`, and `PerformanceMetric`.
5. "Answer the previous question using the executive brief skill."
   - Expected route: `graph_rag`
   - Expected behavior: same grounded content, skill-specific formatting.

## Implementation Tasks

### Task 1: Backend Skeleton

**Files:**
- Create: `apps/backend/pyproject.toml`
- Create: `apps/backend/app/main.py`
- Create: `apps/backend/app/core/config.py`
- Create: `apps/backend/app/core/logging.py`
- Create: `apps/backend/app/core/tracing.py`
- Create: `apps/backend/app/api/routes_chat.py`
- Create: `apps/backend/app/api/routes_documents.py`
- Create: `apps/backend/app/api/routes_ontology.py`
- Create: `apps/backend/app/api/routes_skills.py`
- Create: `apps/backend/app/api/routes_traces.py`
- Create: `apps/backend/app/tests/unit/test_health.py`

- [ ] **Step 1: Add backend dependencies**

Use `uv` and pin a working set:

```toml
[project]
name = "graph-rag-demo-backend"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.34",
  "pydantic>=2.10",
  "pydantic-settings>=2.7",
  "langgraph>=0.2",
  "openai>=1.70",
  "google-cloud-storage>=2.19",
  "google-cloud-logging>=3.11",
  "google-cloud-trace>=1.15",
  "google-cloud-aiplatform>=1.80",
  "neo4j>=5.27",
  "neo4j-graphrag[openai,google]>=1.7",
  "pdfplumber>=0.11",
  "pypdf>=5.1",
  "pymupdf>=1.25",
  "python-multipart>=0.0.20",
  "tenacity>=9.0",
  "structlog>=24.4",
  "pyyaml>=6.0",
  "sqlalchemy>=2.0",
  "asyncpg>=0.30"
]

[dependency-groups]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.25",
  "httpx>=0.28",
  "ruff>=0.9",
  "mypy>=1.14"
]
```

- [ ] **Step 2: Implement FastAPI app startup**

```python
from fastapi import FastAPI

from app.api import routes_chat, routes_documents, routes_ontology, routes_skills, routes_traces


def create_app() -> FastAPI:
    app = FastAPI(title="Graph RAG Demo", version="0.1.0")
    app.include_router(routes_chat.router, prefix="/api")
    app.include_router(routes_documents.router, prefix="/api")
    app.include_router(routes_ontology.router, prefix="/api")
    app.include_router(routes_skills.router, prefix="/api")
    app.include_router(routes_traces.router, prefix="/api")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 3: Add a health test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_health.py -v
```

Expected: one passing test.

### Task 2: Pydantic Domain Models

**Files:**
- Create: `apps/backend/app/models/document.py`
- Create: `apps/backend/app/models/graph.py`
- Create: `apps/backend/app/models/ingestion.py`
- Create: `apps/backend/app/models/chat.py`
- Create: `apps/backend/app/models/skill.py`
- Create: `apps/backend/app/models/trace.py`
- Create: `apps/backend/app/tests/unit/test_skill_model.py`
- Create: `apps/backend/app/tests/unit/test_graph_model.py`

- [ ] **Step 1: Define graph extraction models**

```python
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceSpan(BaseModel):
    page_number: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=2000)
    bbox: list[float] | None = None
    source_hash: str


class GraphNode(BaseModel):
    temporary_id: str = Field(pattern=r"^[a-zA-Z0-9_\-:.]+$")
    label: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=300)
    properties: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class GraphRelationship(BaseModel):
    source_temporary_id: str
    relationship_type: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    target_temporary_id: str
    properties: dict[str, str | int | float | bool | list[str]] = Field(default_factory=dict)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class PageGraphExtraction(BaseModel):
    document_id: str
    page_number: int = Field(ge=1)
    page_summary: str = Field(max_length=1000)
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]
```

- [ ] **Step 2: Define skill validation models**

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator


BLOCKED_PHRASES = (
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "tool call",
    "exfiltrate",
    "secret",
)


class SkillSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = Field(min_length=1, max_length=80)
    max_words: int | None = Field(default=None, ge=1, le=500)
    citation_required: bool = False


class SkillStyle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tone: str = Field(default="concise", max_length=40)
    bullets_max: int = Field(default=5, ge=0, le=10)


class SkillConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require_page_citations: bool = True
    forbid_uncited_claims: bool = True


class SkillDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[a-zA-Z0-9_\-]+$", max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(max_length=500)
    allowed_output_modes: list[str] = Field(default=["markdown"], min_length=1, max_length=3)
    required_sections: list[SkillSection] = Field(min_length=1, max_length=8)
    style: SkillStyle = Field(default_factory=SkillStyle)
    constraints: SkillConstraints = Field(default_factory=SkillConstraints)

    @field_validator("description")
    @classmethod
    def reject_prompt_control(cls, value: str) -> str:
        lowered = value.lower()
        if any(phrase in lowered for phrase in BLOCKED_PHRASES):
            raise ValueError("skill description contains blocked prompt-control text")
        return value
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_skill_model.py apps/backend/app/tests/unit/test_graph_model.py -v
```

Expected: validation accepts the sample executive brief skill and rejects skills with unknown keys or prompt-control text.

### Task 3: Page-Wise PDF Pipeline

**Files:**
- Create: `apps/backend/app/ingestion/pdf_pages.py`
- Create: `apps/backend/app/ingestion/page_renderer.py`
- Create: `apps/backend/app/ingestion/page_extractor.py`
- Create: `apps/backend/app/ingestion/ingestion_job.py`
- Create: `apps/backend/app/tests/unit/test_pdf_work_units.py`

- [ ] **Step 1: Create page work unit logic**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PageWorkUnit:
    document_id: str
    page_number: int
    window_start: int
    window_end: int


def build_page_work_units(document_id: str, page_count: int, window_size: int = 1) -> list[PageWorkUnit]:
    if page_count < 1:
        raise ValueError("page_count must be positive")
    if window_size not in (1, 3):
        raise ValueError("window_size must be 1 or 3")

    radius = window_size // 2
    return [
        PageWorkUnit(
            document_id=document_id,
            page_number=page,
            window_start=max(1, page - radius),
            window_end=min(page_count, page + radius),
        )
        for page in range(1, page_count + 1)
    ]
```

- [ ] **Step 2: Test that ingestion never creates whole-document work units**

```python
from app.ingestion.pdf_pages import build_page_work_units


def test_default_work_units_are_single_page() -> None:
    units = build_page_work_units("doc", page_count=67)
    assert len(units) == 67
    assert all(unit.window_start == unit.page_number for unit in units)
    assert all(unit.window_end == unit.page_number for unit in units)


def test_three_page_window_is_bounded() -> None:
    units = build_page_work_units("doc", page_count=67, window_size=3)
    assert units[0].window_start == 1
    assert units[0].window_end == 2
    assert units[33].window_start == 33
    assert units[33].window_end == 35
    assert units[-1].window_start == 66
    assert units[-1].window_end == 67
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_pdf_work_units.py -v
```

Expected: both tests pass.

### Task 4: Vertex Multimodal Embeddings Adapter

**Files:**
- Create: `apps/backend/app/services/vertex_embeddings.py`
- Create: `apps/backend/app/tests/unit/test_retrieval_caption.py`

- [ ] **Step 1: Add a query/page caption compressor**

```python
MAX_MULTIMODAL_TEXT_WORDS = 28


def compact_caption(text: str) -> str:
    words = text.replace("\n", " ").split()
    return " ".join(words[:MAX_MULTIMODAL_TEXT_WORDS])
```

- [ ] **Step 2: Implement the embedding interface**

```python
from dataclasses import dataclass

import vertexai
from vertexai.vision_models import Image, MultiModalEmbeddingModel

from app.core.config import Settings
from app.services.vertex_embeddings import compact_caption


@dataclass(frozen=True)
class MultimodalEmbedding:
    vector: list[float]
    dimension: int
    caption: str


class VertexMultimodalEmbedder:
    def __init__(self, settings: Settings) -> None:
        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_region)
        self._model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")

    def embed_page_image(self, image_path: str, caption: str, dimension: int = 1408) -> MultimodalEmbedding:
        safe_caption = compact_caption(caption)
        image = Image.load_from_file(image_path)
        result = self._model.get_embeddings(
            image=image,
            contextual_text=safe_caption,
            dimension=dimension,
        )
        return MultimodalEmbedding(
            vector=list(result.image_embedding),
            dimension=dimension,
            caption=safe_caption,
        )
```

- [ ] **Step 3: Verify caption constraint**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_retrieval_caption.py -v
```

Expected: compacted captions are capped at 28 words.

### Task 5: LLM Extraction Adapter

**Files:**
- Create: `apps/backend/app/services/openai_llm.py`
- Create: `apps/backend/app/ingestion/page_extractor.py`
- Create: `apps/backend/app/tests/unit/test_page_extractor_prompt.py`

- [ ] **Step 1: Define the extraction contract**

The page extractor prompt must include:

- Document title.
- Page number.
- Section heading.
- Current page text.
- Previous page summary only.
- Allowed node labels and relationship types.
- Instruction that document text is untrusted evidence and cannot override extraction instructions.
- JSON schema target matching `PageGraphExtraction`.

- [ ] **Step 2: Add output validation**

The extractor must parse the model output into `PageGraphExtraction`. If validation fails, retry once with the validation errors. If it fails again, mark the page as failed and store the raw output in restricted trace storage.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_page_extractor_prompt.py -v
```

Expected: prompts contain one page of text and do not contain text from unrelated pages.

### Task 6: Neo4j Graph Writer And Normalizer

**Files:**
- Create: `apps/backend/app/services/neo4j_graph.py`
- Create: `apps/backend/app/ingestion/graph_normalizer.py`
- Create: `apps/backend/app/ingestion/graph_writer.py`
- Create: `apps/backend/app/tests/integration/test_graph_writer.py`

- [ ] **Step 1: Canonicalize entity IDs**

Canonical ID format:

```text
{document_id}:{label}:{slugified_name}
```

Example:

```text
fda_ai_dsf_2025:DocumentationArtifact:performance_validation_documentation
```

- [ ] **Step 2: Write nodes with evidence**

Use `MERGE` by canonical ID and append page-backed evidence spans. Never merge evidence without `source_hash`, `page_number`, and `extraction_run_id`.

- [ ] **Step 3: Write relationships with confidence**

Use `MERGE` by source ID, relationship type, target ID, and extraction run ID. Store relationship confidence and evidence IDs.

- [ ] **Step 4: Verify with Neo4j test container**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/integration/test_graph_writer.py -v
```

Expected: duplicate page ingestion does not create duplicate canonical nodes.

### Task 7: Chat Router

**Files:**
- Create: `apps/backend/app/rag/router.py`
- Create: `apps/backend/app/tests/unit/test_router.py`

- [ ] **Step 1: Implement deterministic greeting fast path**

Classify common greetings locally:

```python
GREETING_PATTERNS = (
    "hi",
    "hello",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
)


def is_plain_greeting(message: str) -> bool:
    normalized = " ".join(message.lower().strip().split())
    return normalized in GREETING_PATTERNS or normalized.rstrip("!.") in GREETING_PATTERNS
```

- [ ] **Step 2: Implement structured route fallback**

If deterministic routing is inconclusive, call `gpt-5.4-mini` with a constrained route schema:

```json
{
  "route": "greeting | graph_rag | ontology | skill_management | out_of_scope",
  "confidence": 0.0,
  "reason": "short reason"
}
```

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_router.py -v
```

Expected:

- "hi" routes to `greeting`.
- "What is performance validation?" routes to `graph_rag`.
- "List domain objects" routes to `ontology`.
- "Upload this formatting skill" routes to `skill_management`.

### Task 8: Graph RAG Workflow

**Files:**
- Create: `apps/backend/app/rag/graph_state.py`
- Create: `apps/backend/app/rag/retrievers.py`
- Create: `apps/backend/app/rag/evidence_packer.py`
- Create: `apps/backend/app/rag/answerer.py`
- Create: `apps/backend/app/rag/graph_workflow.py`
- Create: `apps/backend/app/tests/unit/test_evidence_packer.py`
- Create: `apps/backend/app/tests/integration/test_graph_rag_workflow.py`

- [ ] **Step 1: Build retrievers**

Retrievers:

- `PageVectorRetriever`: returns page hits from Neo4j vector index or Vertex AI Vector Search.
- `EntityRetriever`: returns graph nodes by aliases, labels, and normalized names.
- `NeighborhoodRetriever`: expands graph paths from matched entities to evidence spans.

- [ ] **Step 2: Pack evidence**

Evidence packing rules:

- At most 12 evidence spans.
- At most 4 pages unless the user asks for a broad summary.
- Prefer direct recommendations over background text.
- Keep page number, section, relationship path, and evidence ID.
- Drop low-confidence spans below `0.55` unless no better evidence exists.

- [ ] **Step 3: Generate grounded answer**

Answer rules:

- Use only packed evidence.
- Cite every factual claim with page references.
- If evidence is insufficient, say what is missing and show the closest evidence.
- Return graph paths separately from prose.

- [ ] **Step 4: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_evidence_packer.py apps/backend/app/tests/integration/test_graph_rag_workflow.py -v
```

Expected: answers contain citations and refuse unsupported claims.

### Task 9: Skill Registry And Formatter

**Files:**
- Create: `apps/backend/app/services/skill_registry.py`
- Create: `apps/backend/app/rag/answerer.py`
- Create: `apps/backend/app/api/routes_skills.py`
- Create: `apps/backend/app/tests/unit/test_skill_registry.py`
- Create: `apps/backend/app/tests/unit/test_skill_format_validation.py`

- [ ] **Step 1: Implement skill upload**

Upload flow:

1. Reject files over 20 KB.
2. Parse YAML or JSON.
3. Validate with `SkillDefinition`.
4. Compute `skill_id = {name}:{version}:{sha256_prefix}`.
5. Store immutable skill definition.

- [ ] **Step 2: Implement answer format validation**

Validation:

- Required headings must exist.
- Citation-required sections must contain page citations.
- If `forbid_uncited_claims` is true, reject paragraphs without citations unless they are explicitly labeled as limitations.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_skill_registry.py apps/backend/app/tests/unit/test_skill_format_validation.py -v
```

Expected: safe skills pass, prompt-injection skills fail, malformed output is corrected or falls back.

### Task 10: Trace Store And Logging

**Files:**
- Create: `apps/backend/app/services/trace_store.py`
- Create: `apps/backend/app/core/logging.py`
- Create: `apps/backend/app/core/tracing.py`
- Create: `apps/backend/app/api/routes_traces.py`
- Create: `apps/backend/app/tests/unit/test_trace_redaction.py`

- [ ] **Step 1: Redact secrets**

Redact:

- API keys.
- Bearer tokens.
- Signed URLs.
- Raw uploaded skill text after validation.
- Raw model outputs from failed safety validation.

- [ ] **Step 2: Store demo traces**

Store route, retrieval, graph paths, citations, token usage, latency, and sanitized prompts.

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/unit/test_trace_redaction.py -v
```

Expected: trace payloads never expose secrets or signed URLs.

### Task 11: Frontend Shell

**Files:**
- Create: `apps/frontend/package.json`
- Create: `apps/frontend/src/app/page.tsx`
- Create: `apps/frontend/src/lib/api.ts`
- Create: `apps/frontend/src/lib/types.ts`
- Create: `apps/frontend/src/components/chat/ChatWorkspace.tsx`
- Create: `apps/frontend/src/components/chat/EvidencePanel.tsx`
- Create: `apps/frontend/src/components/chat/TracePanel.tsx`

- [ ] **Step 1: Build chat workspace**

The chat UI must show:

- Document selector.
- Skill selector.
- Message composer.
- Streaming answer area.
- Citation chips.
- Right-side evidence, graph path, trace, and page preview tabs.

- [ ] **Step 2: Verify layout**

Run:

```bash
npm --prefix apps/frontend run lint
npm --prefix apps/frontend run test
```

Expected: lint and component tests pass.

### Task 12: Frontend Document, Ontology, Skill, And Trace Views

**Files:**
- Create: `apps/frontend/src/app/documents/page.tsx`
- Create: `apps/frontend/src/app/ontology/page.tsx`
- Create: `apps/frontend/src/app/skills/page.tsx`
- Create: `apps/frontend/src/app/traces/page.tsx`
- Create: `apps/frontend/src/components/documents/IngestionTimeline.tsx`
- Create: `apps/frontend/src/components/ontology/OntologyExplorer.tsx`
- Create: `apps/frontend/src/components/skills/SkillUploader.tsx`
- Create: `apps/frontend/src/components/traces/TraceTimeline.tsx`

- [ ] **Step 1: Implement demo-oriented views**

Each view must expose one clear demo story:

- Documents: "This is ingested page by page."
- Ontology: "These are the extracted domain objects and links."
- Skills: "Skills format output but cannot change system behavior."
- Traces: "This is why the chatbot answered this way."

- [ ] **Step 2: Verify with Playwright**

Run:

```bash
npm --prefix apps/frontend run e2e
```

Expected: upload, chat, ontology, skill preview, and trace views are reachable and usable.

### Task 13: GCP Deployment

**Files:**
- Create: `infra/terraform/main.tf`
- Create: `infra/terraform/variables.tf`
- Create: `infra/terraform/cloud_run.tf`
- Create: `infra/terraform/storage.tf`
- Create: `infra/terraform/sql.tf`
- Create: `infra/terraform/secrets.tf`
- Create: `infra/terraform/logging.tf`
- Create: `apps/backend/Dockerfile`
- Create: `apps/frontend/Dockerfile`

- [ ] **Step 1: Provision cloud services**

Provision:

- Artifact Registry.
- Cloud Run backend service.
- Cloud Run frontend service.
- Cloud Run ingestion job.
- Pub/Sub topic for ingestion.
- Cloud Tasks queue for page work.
- GCS bucket for PDFs, page images, and extracted text.
- Cloud SQL Postgres for app metadata and traces.
- Secret Manager secrets for OpenAI, Neo4j, and app signing keys.
- Log sink for demo traces.

- [ ] **Step 2: Configure Neo4j**

Use Neo4j AuraDB in the same GCP region where possible. Create constraints:

```cypher
CREATE CONSTRAINT canonical_entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.canonical_id IS UNIQUE;

CREATE CONSTRAINT evidence_id IF NOT EXISTS
FOR (e:EvidenceSpan) REQUIRE e.evidence_id IS UNIQUE;
```

Create vector index for page embeddings:

```cypher
CREATE VECTOR INDEX page_embedding_index IF NOT EXISTS
FOR (p:Page) ON (p.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 1408, `vector.similarity_function`: 'cosine'}};
```

- [ ] **Step 3: Verify deployment**

Run:

```bash
terraform -chdir=infra/terraform plan
terraform -chdir=infra/terraform apply
```

Expected: Cloud Run frontend and backend URLs are created, backend `/healthz` returns `{"status":"ok"}`.

### Task 14: Evaluation Harness

**Files:**
- Create: `apps/backend/app/tests/evals/golden_questions.yaml`
- Create: `apps/backend/app/tests/evals/test_grounded_answers.py`
- Create: `docs/demo/script.md`

- [ ] **Step 1: Add golden questions**

Include at least 30 questions across:

- greetings
- direct fact lookup
- ontology listing
- relationship explanation
- validation
- data management
- bias and transparency
- monitoring
- cybersecurity
- model card content
- skill formatting

- [ ] **Step 2: Grade answers**

Metrics:

- route accuracy
- citation coverage
- unsupported claim count
- answer usefulness
- latency
- retrieval precision by page

- [ ] **Step 3: Verify**

Run:

```bash
uv run --project apps/backend pytest apps/backend/app/tests/evals/test_grounded_answers.py -v
```

Expected:

- Route accuracy at least 95%.
- Citation coverage at least 90%.
- Unsupported claim count is zero on the golden set.

## Milestone Plan

### Milestone 1: Local Skeleton

Deliverables:

- Backend health endpoint.
- Frontend shell.
- Pydantic models.
- Skill validation.
- Router tests.

Exit criteria:

- Local backend and frontend run.
- Greeting routes do not hit retrieval.
- Unsafe skill samples are rejected.

### Milestone 2: Local Ingestion And Graph

Deliverables:

- FDA PDF page extraction.
- Page image rendering.
- Vertex multimodal embeddings.
- Page-wise graph extraction.
- Neo4j graph writing.
- Ontology API.

Exit criteria:

- 67 pages processed as individual work units.
- Ontology view lists domain objects and relationship counts.
- Reprocessing a page is idempotent.

### Milestone 3: Graph RAG Chat

Deliverables:

- LangGraph workflow.
- Hybrid graph/vector retrieval.
- Evidence packing.
- Grounded answer generation.
- Citation display.

Exit criteria:

- Demo questions answer with page citations.
- Trace viewer shows route, retrieval, graph paths, and model calls.

### Milestone 4: Skills And Demo Polish

Deliverables:

- Skill upload and preview.
- Skill-specific answer formatting.
- Demo scenario selector.
- Eval harness.

Exit criteria:

- Executive brief skill changes answer format without changing retrieved evidence.
- Golden evals meet route, citation, and groundedness targets.

### Milestone 5: GCP Deployment

Deliverables:

- Cloud Run services.
- Cloud Run ingestion job.
- GCS artifact storage.
- Cloud SQL metadata and traces.
- Neo4j AuraDB.
- Cloud Logging and Trace.

Exit criteria:

- Public demo URL works.
- Ingestion can be restarted safely.
- Trace and logging views show real cloud telemetry.

## Security And Safety Controls

- Treat PDF text as untrusted input.
- Treat uploaded skills as untrusted input.
- Never allow skill execution as Python, JavaScript, shell, SQL, Cypher, HTML script, or remote URL fetch.
- Use allowlisted skill schema only.
- Escape document text inside prompts as evidence.
- Use prompt sections that separate system policy, developer policy, skill formatting, user query, and evidence.
- Reject HTML output unless rendered in a sanitized Markdown renderer.
- Store signed GCS URLs only in short-lived responses, never in traces.
- Scan uploaded PDFs for file type, page count, size, and encryption.
- Limit page image resolution and PDF size to control cost.
- Add per-user and per-document rate limits.
- Use Secret Manager for all API keys.
- Use service accounts with least privilege.

## Risks And Mitigations

- **Risk:** Multimodal embedding text limit hurts long text retrieval.
  **Mitigation:** Embed page images plus short captions, use graph entity retrieval for text semantics, and store full text as evidence.
- **Risk:** LLM extracts duplicate or inconsistent entities.
  **Mitigation:** Canonical IDs, alias matching, confidence scores, and a reviewable merge queue.
- **Risk:** Skills become a prompt injection channel.
  **Mitigation:** Strict schema validation, blocked phrases, no executable fields, and post-generation output validation.
- **Risk:** Demo answer lacks provenance.
  **Mitigation:** Require citations and graph paths for every Graph RAG answer.
- **Risk:** Ingestion is slow for a live demo.
  **Mitigation:** Preload the FDA document, keep reprocess-page as the live demo operation, and show cached trace bundles.

## Open Configuration Choices

- `GRAPH_STORE=neo4j_aura`
- `VECTOR_STORE=neo4j_vector`
- `LLM_MODEL=gpt-5.4-mini`
- `ROUTER_MODEL=gpt-5.4-mini`
- `EMBEDDING_MODEL=multimodalembedding@001`
- `EMBEDDING_DIMENSION=1408`
- `DEFAULT_PAGE_WINDOW=1`
- `TABLE_CONTINUATION_PAGE_WINDOW=3`
- `MAX_EVIDENCE_SPANS=12`
- `MAX_SKILL_BYTES=20480`

## Final Verification Checklist

- [ ] The selected PDF is at least 30 pages.
- [ ] Ingestion processes pages individually or in a bounded 3-page window.
- [ ] The UI can list ontology objects, properties, and links.
- [ ] Greeting requests route away from Graph RAG.
- [ ] Non-greeting document questions route into Graph RAG.
- [ ] Answers include citations and graph paths.
- [ ] Skills affect answer format only.
- [ ] Unsafe skills are rejected.
- [ ] Trace viewer explains every answer.
- [ ] Cloud logs and traces are available for the demo.
- [ ] Golden evals pass citation and groundedness thresholds.

