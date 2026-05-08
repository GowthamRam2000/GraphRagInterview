"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Clock,
  Database,
  GitBranch,
  Loader2,
  MessageSquare,
  Network,
  SearchCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { GraphPathView } from "@/components/GraphPathView";
import {
  TraceOverview,
} from "@/components/TraceOverview";
import {
  TraceSpanDetail,
} from "@/components/TraceSpanDetail";
import type { TraceSpan } from "@/components/TraceWaterfall";
import {
  TraceWaterfall,
} from "@/components/TraceWaterfall";
import {
  getOntology,
  getSearchPreview,
  getSmoke,
  getTrace,
  listDocuments,
  listTraces,
} from "@/lib/api";
import type {
  DocumentSummary,
  OntologyResponse,
  SearchPreview,
  SmokeResult,
  TraceDetail,
  TraceSummary,
} from "@/lib/types";

export function TraceExplorer() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [ontology, setOntology] = useState<OntologyResponse | null>(null);
  const [preview, setPreview] = useState<SearchPreview | null>(null);
  const [smoke, setSmoke] = useState<SmokeResult | null>(null);
  const [query, setQuery] = useState("secure and resilient AI systems");
  const [status, setStatus] = useState("Ready");
  const [selectedSpan, setSelectedSpan] = useState<TraceSpan | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.document_id === selectedDocumentId),
    [documents, selectedDocumentId]
  );

  const spans = useMemo(() => deriveSpans(trace), [trace]);

  async function refresh() {
    setStatus("Refreshing");
    const [nextDocuments, nextTraces, nextSmoke] = await Promise.all([
      listDocuments(),
      listTraces(),
      getSmoke(),
    ]);
    setDocuments(nextDocuments);
    setTraces(nextTraces);
    setSmoke(nextSmoke);
    const storedDocument = window.localStorage.getItem("lastDocumentId") || "";
    const documentId = storedDocument || nextTraces[0]?.document_id || nextDocuments.at(-1)?.document_id || "";
    setSelectedDocumentId(documentId);
    if (documentId) setOntology(await getOntology(documentId));
    const storedTrace = window.localStorage.getItem("lastTraceId") || nextTraces[0]?.trace_id || "";
    if (storedTrace) {
      const detail = await getTrace(storedTrace);
      setTrace(detail);
      setSelectedSpan(null);
    }
    setStatus("Ready");
  }

  useEffect(() => {
    queueMicrotask(() => {
      void refresh();
    });
  }, []);

  async function openTrace(traceId: string) {
    setStatus("Loading trace");
    const detail = await getTrace(traceId);
    setTrace(detail);
    setSelectedSpan(null);
    window.localStorage.setItem("lastTraceId", traceId);
    if (detail.document_id) {
      setSelectedDocumentId(detail.document_id);
      setOntology(await getOntology(detail.document_id));
    }
    setStatus("Ready");
  }

  async function runPreview() {
    if (!selectedDocumentId) return;
    setStatus("Searching");
    setPreview(await getSearchPreview(selectedDocumentId, query));
    setStatus("Ready");
  }

  return (
    <main className="trace-page">
      <AnimatePresence>
        {(status === "Refreshing" || status === "Loading trace") && (
          <motion.div
            className="trace-fullscreen-loader"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <div className="trace-loader-glass">
              <Loader2 className="spin" size={40} />
              <h2>{status === "Refreshing" ? "Loading traces" : "Loading trace"}</h2>
              <p>Please wait a moment</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <section className="trace-hero">
        <div>
          <p className="eyebrow">Trace console</p>
          <h1>Explain how an answer was selected.</h1>
          <p>Inspect route, retrieval candidates, ranker scores, ontology objects, graph links, and cloud health.</p>
        </div>
        <div className="status-pill">
          {status === "Ready" ? <Activity size={15} /> : <Loader2 className="spin" size={15} />}
          {status}
        </div>
      </section>

      <section className="trace-workspace">
        {/* Left: Document + Trace List */}
        <aside className="trace-list-col">
          <div className="workspace-panel">
            <div className="panel-header">
              <h2>
                <Database size={18} /> Documents
              </h2>
            </div>
            <div className="document-list">
              {documents.map((document) => (
                <button
                  key={document.document_id}
                  className={
                    document.document_id === selectedDocumentId
                      ? "select-row active"
                      : "select-row"
                  }
                  onClick={() => {
                    setSelectedDocumentId(document.document_id);
                    void getOntology(document.document_id).then(setOntology);
                    window.localStorage.setItem("lastDocumentId", document.document_id);
                  }}
                >
                  <span>{document.filename}</span>
                  <small>
                    {document.page_count} pages · {document.status}
                  </small>
                </button>
              ))}
            </div>
          </div>

          <div className="workspace-panel">
            <div className="panel-header">
              <h2>
                <Clock size={18} /> Traces
              </h2>
            </div>
            <div className="trace-buttons">
              {status === "Refreshing" && traces.length === 0 ? (
                <div className="trace-loading">
                  <Loader2 className="spin" size={18} />
                  <span>Loading traces...</span>
                </div>
              ) : (
                traces.map((item) => (
                  <button
                    key={item.trace_id}
                    className={item.trace_id === trace?.trace_id ? "select-row active" : "select-row"}
                    onClick={() => void openTrace(item.trace_id)}
                  >
                    <span>{item.route}</span>
                    <small>{item.trace_id}</small>
                  </button>
                ))
              )}
            </div>
          </div>
        </aside>

        {/* Center: Overview + Waterfall + Search Preview */}
        <section className="trace-main-col">
          {trace ? (
            <>
              <TraceOverview trace={trace} />

              <TraceWaterfall
                spans={spans}
                totalDuration={spans.length ? Math.max(...spans.map((s) => s.end_time)) : 1}
                onSelectSpan={setSelectedSpan}
                selectedSpanId={selectedSpan?.id}
              />

              {/* Retrieval timeline (legacy, kept for detail) */}
              <motion.div
                className="trace-card"
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <h2>
                  <SearchCheck size={19} /> Retrieval timeline
                </h2>
                {trace.retrieval.length ? (
                  <div className="timeline">
                    {trace.retrieval.map((item, index) => (
                      <div key={item.evidence_id} className="timeline-row">
                        <span>{index + 1}</span>
                        <div>
                          <strong>Page {item.page_number}</strong>
                          <p>{item.entities.slice(0, 5).join(", ") || "Evidence span"}</p>
                          <div className="score-bars">
                            <Score label="semantic" value={item.semantic_score} />
                            <Score label="lexical" value={item.lexical_score} />
                            <Score label="rerank" value={item.rerank_score ?? undefined} />
                            <Score label="final" value={item.final_score} />
                          </div>
                        </div>
                        <em>{item.ranker ?? "local"}</em>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">No retrieval data.</p>
                )}
              </motion.div>

              {/* Search preview */}
              <div className="trace-card">
                <h2>
                  <Database size={19} /> Search preview
                </h2>
                <div className="search-line">
                  <input
                    className="ui-field"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                  <button className="ui-button" onClick={() => void runPreview()}>
                    Rank
                  </button>
                </div>
                {preview ? (
                  <div className="preview-results">
                    {preview.results.slice(0, 6).map((item) => (
                      <article key={item.evidence_id}>
                        <strong>Page {item.page_number}</strong>
                        <span>
                          {item.ranker} final {item.final_score.toFixed(3)}
                        </span>
                        <p>{item.text}</p>
                      </article>
                    ))}
                  </div>
                ) : null}
              </div>
            </>
          ) : (
            <motion.div
              className="trace-card"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <p className="muted">Select a trace from the left panel to inspect execution details.</p>
            </motion.div>
          )}
        </section>

        {/* Right: Detail Panel */}
        <aside className="trace-detail-col">
          {selectedSpan ? (
            <TraceSpanDetail span={selectedSpan} trace={trace!} />
          ) : (
            <>
              <div className="trace-card">
                <h2>
                  <Network size={19} /> Ontology
                </h2>
                <p className="muted">{selectedDocument?.filename ?? "No document selected"}</p>
                {ontology ? (
                  <div className="ontology-map">
                    {ontology.object_types.map((item, index) => (
                      <div key={item.label} style={{ animationDelay: `${index * 90}ms` }}>
                        <strong>{item.label}</strong>
                        <span>{item.count}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
              <div className="trace-card">
                <h2>
                  <GitBranch size={19} /> Graph paths
                </h2>
                {trace?.graph_paths.length ? (
                  <GraphPathView paths={trace.graph_paths} />
                ) : (
                  <p className="muted">No graph paths selected.</p>
                )}
              </div>
              <div className="trace-card">
                <h2>
                  <MessageSquare size={19} /> Model
                </h2>
                {trace?.model_calls?.length && trace.model_calls[0].model ? (
                  <div className="metric-grid">
                    <div>
                      <span>Model</span>
                      <strong>{String(trace.model_calls[0].model)}</strong>
                    </div>
                    <div>
                      <span>Tokens</span>
                      <strong>{String(trace.usage?.total_tokens ?? "n/a")}</strong>
                    </div>
                  </div>
                ) : (
                  <p className="muted">Model usage appears after the first answer.</p>
                )}
              </div>
              <div className="trace-card">
                <h2>
                  <Activity size={19} /> Smoke
                </h2>
                {smoke?.checks.map((check) => (
                  <div key={check.name} className="health-row">
                    <span>{check.name}</span>
                    <strong>{check.ok ? "ok" : "fail"}</strong>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </section>
    </main>
  );
}

function Score({ label, value }: { label: string; value?: number }) {
  const width = Math.max(8, Math.min(100, Math.abs(value ?? 0) * 18));
  return (
    <div>
      <span>{label}</span>
      <i>
        <b style={{ width: `${width}%` }} />
      </i>
      <strong>{typeof value === "number" ? value.toFixed(3) : "n/a"}</strong>
    </div>
  );
}

function deriveSpans(trace: TraceDetail | null): TraceSpan[] {
  if (!trace) return [];

  const spans: TraceSpan[] = [];
  let cursor = 0;

  // 1. Retrieval span
  if (trace.retrieval.length) {
    const duration = getTiming(trace.timings, "retrieval") || getTiming(trace.timings, "retrieve") || 200;
    spans.push({
      id: "span-retrieval",
      name: "Retrieve evidence",
      type: "retrieval",
      start_time: cursor,
      end_time: cursor + duration,
      duration_ms: duration,
      status: "success",
      output: { candidates: trace.retrieval.length, top_pages: trace.retrieval.slice(0, 3).map((r) => r.page_number) },
    });
    cursor += duration;
  }

  // 2. Reranking span
  if (trace.retrieval.some((r) => r.rerank_score !== null)) {
    const duration = getTiming(trace.timings, "reranking") || getTiming(trace.timings, "rerank") || 150;
    spans.push({
      id: "span-reranking",
      name: "Rerank results",
      type: "reranking",
      start_time: cursor,
      end_time: cursor + duration,
      duration_ms: duration,
      status: "success",
    });
    cursor += duration;
  }

  // 3. Graph query span
  if (trace.graph_paths.length) {
    const duration = getTiming(trace.timings, "graph_query") || getTiming(trace.timings, "graph") || 100;
    spans.push({
      id: "span-graph",
      name: "Graph paths",
      type: "graph_query",
      start_time: cursor,
      end_time: cursor + duration,
      duration_ms: duration,
      status: "success",
      output: { paths_found: trace.graph_paths.length },
    });
    cursor += duration;
  }

  // 4. Generation spans from model_calls
  if (trace.model_calls?.length) {
    trace.model_calls.forEach((call, idx) => {
      const duration = getTiming(trace.timings, "generation") || getTiming(trace.timings, "generate") || getTiming(trace.timings, "llm") || 800;
      spans.push({
        id: `span-generation-${idx}`,
        name: String(call.purpose ?? "Generate answer"),
        type: "generation",
        parent_id: idx > 0 ? `span-generation-${idx - 1}` : undefined,
        start_time: cursor,
        end_time: cursor + duration,
        duration_ms: duration,
        status: (call.status as string) === "error" ? "error" : "success",
        input: call.prompts ? { prompts: call.prompts } : undefined,
        output: { model: call.model, tokens: call.tokens },
        metadata: call as Record<string, unknown>,
      });
      cursor += duration;
    });
  }

  // 5. Fallback / other spans
  if (trace.route === "fallback" || trace.route === "out_of_scope") {
    spans.push({
      id: "span-fallback",
      name: "Fallback handler",
      type: "other",
      start_time: cursor,
      end_time: cursor + 50,
      duration_ms: 50,
      status: "success",
    });
  }

  return spans;
}

function getTiming(timings: Record<string, unknown> | undefined, key: string): number | undefined {
  if (!timings) return undefined;
  const val = timings[key];
  if (typeof val === "number") return val;
  if (typeof val === "string") {
    const parsed = parseFloat(val);
    return isNaN(parsed) ? undefined : parsed;
  }
  return undefined;
}
