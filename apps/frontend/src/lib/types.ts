export interface DocumentSummary {
  document_id: string;
  filename: string;
  title: string | null;
  status: string;
  page_count: number;
}

export interface UploadResponse {
  document: {
    document_id: string;
    upload_url: string;
    gcs_uri: string;
    status: string;
  };
  ingestion: IngestionStatus;
  parser: string;
}

export interface PageStatus {
  page_number: number;
  status: string;
  entity_count: number;
  evidence_count: number;
  error?: string | null;
}

export interface IngestionStatus {
  document_id: string;
  status: string;
  page_count: number;
  pages: PageStatus[];
}

export interface OntologyResponse {
  document_id: string;
  object_types: Array<{
    label: string;
    count: number;
    properties: string[];
    examples: string[];
  }>;
  relationships: Array<{
    type: string;
    source_label: string;
    target_label: string;
    count: number;
    examples: string[];
  }>;
}

export interface Citation {
  page_number: number;
  evidence_id: string;
  text: string;
}

export interface ChatResponse {
  answer: string;
  route: "greeting" | "graph_rag" | "ontology" | "skill_management" | "out_of_scope";
  citations: Citation[];
  graph_paths: string[][];
  trace_id: string;
}

export interface SearchPreviewResult {
  evidence_id: string;
  page_number: number;
  text: string;
  semantic_score: number;
  lexical_score: number;
  combined_score: number;
  rerank_score: number | null;
  final_score: number;
  ranker: string;
  fallback_reason: string | null;
}

export interface SearchPreview {
  document_id: string;
  query: string;
  results: SearchPreviewResult[];
}

export interface SkillDefinition {
  name: string;
  version: string;
  description: string;
  output_mode: "markdown" | "json";
  required_sections: Array<{
    heading: string;
    max_words?: number | null;
    citation_required?: boolean;
  }>;
  tone: "concise" | "executive" | "technical" | "audit" | "cyber";
  citation_style: "page" | "footnote" | "inline";
  require_citations: boolean;
}

export interface SkillResponse {
  skill_id: string;
  definition: SkillDefinition;
}

export interface TraceSummary {
  trace_id: string;
  route: string;
  document_id: string | null;
  created_at: number;
}

export interface TraceDetail extends TraceSummary {
  user_message: string;
  retrieval: Array<{
    evidence_id: string;
    page_number: number;
    entities: string[];
    semantic_score?: number;
    lexical_score?: number;
    combined_score?: number;
    rerank_score?: number | null;
    final_score?: number;
    ranker?: string;
    fallback_reason?: string | null;
  }>;
  evidence: unknown[];
  graph_paths: string[][];
  answer: string;
  prompts?: Array<Record<string, unknown>>;
  model_calls?: Array<Record<string, unknown>>;
  usage?: Record<string, unknown>;
  timings?: Record<string, unknown>;
  cache?: Record<string, unknown>;
}

export interface SmokeResult {
  ok: boolean;
  checks: Array<{
    name: string;
    ok: boolean;
    detail: string;
  }>;
}
