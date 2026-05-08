import type {
  ChatResponse,
  DocumentSummary,
  IngestionStatus,
  OntologyResponse,
  SearchPreview,
  SkillDefinition,
  SkillResponse,
  SmokeResult,
  TraceDetail,
  TraceSummary,
  UploadResponse
} from "@/lib/types";
import { extractSseFrames, parseSseFrame } from "@/lib/streaming";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export const DEMO_API_KEY = process.env.NEXT_PUBLIC_DEMO_API_KEY ?? "dev-local-auth-key";

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("x-api-key", DEMO_API_KEY);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${path} failed with ${response.status}: ${detail}`);
  }
  return response.json() as Promise<T>;
}

export async function getBackendHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/healthz`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Backend health request failed with ${response.status}`);
  }
  return response.json() as Promise<{ status: string }>;
}

export function getSecuredReady(path: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(path);
}

export function listDocuments(): Promise<DocumentSummary[]> {
  return apiFetch<DocumentSummary[]>("/v1/documents");
}

export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<UploadResponse>("/v1/documents/upload", {
    method: "POST",
    body: form
  });
}

export function getIngestion(documentId: string): Promise<IngestionStatus> {
  return apiFetch<IngestionStatus>(`/v1/documents/${documentId}/ingestion`);
}

export function getOntology(documentId: string): Promise<OntologyResponse> {
  return apiFetch<OntologyResponse>(`/v1/documents/${documentId}/ontology`);
}

export function getSearchPreview(documentId: string, query: string): Promise<SearchPreview> {
  const params = new URLSearchParams({ q: query, limit: "8" });
  return apiFetch<SearchPreview>(`/v1/documents/${documentId}/search-preview?${params}`);
}

export function sendChat(input: {
  document_id?: string;
  message: string;
  skill_id?: string;
}): Promise<ChatResponse> {
  return apiFetch<ChatResponse>("/v1/chat", {
    method: "POST",
    body: JSON.stringify(input),
    headers: {
      "content-type": "application/json"
    }
  });
}

export async function sendChatStream(
  input: { document_id?: string; message: string; skill_id?: string },
  onEvent: (event: { event: string; data: string }) => void
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/chat/stream`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "content-type": "application/json",
      "x-api-key": DEMO_API_KEY
    },
    body: JSON.stringify(input)
  });
  if (!response.ok || !response.body) {
    throw new Error(`/v1/chat/stream failed with ${response.status}: ${await response.text()}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { frames, rest } = extractSseFrames(buffer);
    buffer = rest;
    for (const frame of frames) {
      const event = parseSseFrame(frame);
      if (event) onEvent(event);
    }
  }
  const finalFrame = parseSseFrame(buffer);
  if (finalFrame) onEvent(finalFrame);
}

export function listSkills(): Promise<SkillResponse[]> {
  return apiFetch<SkillResponse[]>("/v1/skills");
}

export function createSkill(definition: SkillDefinition): Promise<SkillResponse> {
  return apiFetch<SkillResponse>("/v1/skills", {
    method: "POST",
    body: JSON.stringify(definition),
    headers: {
      "content-type": "application/json"
    }
  });
}

export function uploadSkill(file: File): Promise<SkillResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<SkillResponse>("/v1/skills/upload", {
    method: "POST",
    body: form
  });
}

export function previewSkill(skillId: string): Promise<{ skill_id: string; formatted_answer: string }> {
  return apiFetch<{ skill_id: string; formatted_answer: string }>(`/v1/skills/${skillId}/preview`, {
    method: "POST"
  });
}

export function listTraces(): Promise<TraceSummary[]> {
  return apiFetch<TraceSummary[]>("/v1/traces");
}

export function getTrace(traceId: string): Promise<TraceDetail> {
  return apiFetch<TraceDetail>(`/v1/traces/${traceId}`);
}

export function getSmoke(): Promise<SmokeResult> {
  return apiFetch<SmokeResult>("/v1/traces/admin/smoke");
}

export const cyberSkillTemplate: SkillDefinition = {
  name: "cyber_risk_brief",
  version: "1.0.0",
  description: "Cyber risk analyst response format with controls and residual risk.",
  output_mode: "markdown",
  required_sections: [
    { heading: "Cyber Risk Finding", max_words: 90 },
    { heading: "Relevant Controls", citation_required: true },
    { heading: "Residual Risk", max_words: 70 }
  ],
  tone: "cyber",
  citation_style: "page",
  require_citations: true
};
