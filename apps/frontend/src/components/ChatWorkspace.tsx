"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  Bot,
  ChevronRight,
  FileText,
  Loader2,
  Menu,
  MessageSquare,
  PenLine,
  Send,
  ShieldCheck,
  Upload,
  X
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import rehypeRaw from "rehype-raw";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { GraphPathView } from "@/components/GraphPathView";
import {
  createSkill,
  cyberSkillTemplate,
  getOntology,
  getTrace,
  listDocuments,
  listSkills,
  previewSkill,
  sendChatStream,
  uploadDocument,
  uploadSkill
} from "@/lib/api";
import { revealNextCharacter } from "@/lib/streaming";
import type {
  Citation,
  DocumentSummary,
  OntologyResponse,
  SkillResponse,
  TraceDetail,
  UploadResponse
} from "@/lib/types";

const prompts = [
  "What are the four core functions in the AI Risk Management Framework?",
  "How should AI systems be made secure and resilient?",
  "Assess secure and resilient AI risks for a cyber risk review."
];

const progressLabels: Record<string, string> = {
  hydrating: "Connecting to persisted graph",
  retrieving: "Retrieving evidence",
  reranking: "Reranking results",
  building_prompt: "Preparing grounded prompt",
  generating: "Generating answer",
  fallback: "Fallback answer used",
  saving_trace: "Saving trace"
};

interface ChatTurn {
  question: string;
  answer: string;
  route: string;
  citations: Citation[];
  graph_paths: string[][];
  trace_id: string;
}

interface ChatSession {
  id: string;
  documentId: string;
  documentName: string;
  turns: ChatTurn[];
  createdAt: number;
}

function generateId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function loadSessions(): ChatSession[] {
  try {
    const raw = window.localStorage.getItem("chatSessions");
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown[];
    if (!Array.isArray(parsed)) {
      window.localStorage.removeItem("chatSessions");
      return [];
    }
    const valid = parsed.filter((item): item is ChatSession => {
      const s = item as Partial<ChatSession>;
      return (
        typeof s.id === "string" &&
        typeof s.documentId === "string" &&
        Array.isArray(s.turns)
      );
    });
    if (valid.length !== parsed.length) {
      window.localStorage.removeItem("chatSessions");
      return [];
    }
    return valid;
  } catch {
    return [];
  }
}

function saveSessions(sessions: ChatSession[]) {
  window.localStorage.setItem("chatSessions", JSON.stringify(sessions));
}

export function ChatWorkspace() {
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState("");
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [selectedSkillId, setSelectedSkillId] = useState("");
  const [skillPreview, setSkillPreview] = useState("");
  const [skillName, setSkillName] = useState("executive_risk_brief");
  const [skillSections, setSkillSections] = useState("Executive Summary\nEvidence Used\nRecommended Next Step");
  const [skillDrawerOpen, setSkillDrawerOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState("");
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [visibleAnswer, setVisibleAnswer] = useState("");
  const [streamingRoute, setStreamingRoute] = useState("");
  const [progress, setProgress] = useState<string[]>([]);
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [ontology, setOntology] = useState<OntologyResponse | null>(null);

  const currentSession = useMemo(
    () => sessions.find((s) => s.id === currentSessionId),
    [sessions, currentSessionId]
  );
  const history = currentSession?.turns ?? [];

  const answerBufferRef = useRef("");
  const animationRef = useRef<number | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.document_id === selectedDocumentId),
    [documents, selectedDocumentId]
  );
  const selectedSkill = useMemo(
    () => skills.find((skill) => skill.skill_id === selectedSkillId),
    [skills, selectedSkillId]
  );

  function startNewSession(documentId: string, documentName: string, timestamp?: number) {
    const session: ChatSession = {
      id: generateId(),
      documentId,
      documentName,
      turns: [],
      createdAt: timestamp || Date.now()
    };
    setSessions((current) => {
      const nextSessions = [...current, session];
      saveSessions(nextSessions);
      return nextSessions;
    });
    setSelectedDocumentId(documentId);
    setCurrentSessionId(session.id);
    window.localStorage.setItem("lastSessionId", session.id);
    window.localStorage.setItem("lastDocumentId", documentId);
    setCurrentQuestion("");
    setVisibleAnswer("");
    setStreamCitations([]);
    setStreamingRoute("");
    setProgress([]);
    setTrace(null);
    setUploadResult(null);
    setOntology(null);
  }

  function loadSession(sessionId: string) {
    const session = sessions.find((s) => s.id === sessionId);
    if (!session) return;
    setCurrentSessionId(sessionId);
    window.localStorage.setItem("lastSessionId", sessionId);
    setSelectedDocumentId(session.documentId);
    setCurrentQuestion("");
    setVisibleAnswer("");
    setStreamCitations([]);
    setStreamingRoute("");
    setProgress([]);
    setTrace(null);
    setUploadResult(null);
    setOntology(null);
    if (session.documentId) {
      void run("Loading document", async () => {
        setOntology(await getOntology(session.documentId));
      });
    }
  }

  function updateCurrentSessionTurns(turns: ChatTurn[]) {
    const targetSessionId = currentSessionId || generateId();
    if (!currentSessionId) {
      setCurrentSessionId(targetSessionId);
      window.localStorage.setItem("lastSessionId", targetSessionId);
    }
    setSessions((current) => {
      const existing = current.some((s) => s.id === targetSessionId);
      const nextSessions = existing
        ? current.map((s) => (s.id === targetSessionId ? { ...s, turns } : s))
        : [
            ...current,
            {
              id: targetSessionId,
              documentId: selectedDocumentId,
              documentName: selectedDocument?.filename ?? "Document",
              turns,
              createdAt: Date.now()
            }
          ];
      saveSessions(nextSessions);
      return nextSessions;
    });
  }

  async function run(label: string, action: () => Promise<void>) {
    setError("");
    setStatus(label);
    try {
      await action();
      setStatus("Ready");
    } catch (caught) {
      setStatus("Needs attention");
      setError(friendlyError(caught));
    }
  }

  async function refreshAll(preferredDocumentId?: string) {
    await run("Loading workspace", async () => {
      const [nextDocuments, nextSkills] = await Promise.all([listDocuments(), listSkills()]);
      setDocuments(nextDocuments);
      setSkills(nextSkills);
      const preferredExists = nextDocuments.some((document) => document.document_id === preferredDocumentId);
      const documentId =
        preferredExists && preferredDocumentId
          ? preferredDocumentId
          : selectedDocumentId || nextDocuments.at(-1)?.document_id || "";
      if (!documentId) {
        setSelectedDocumentId("");
      } else if (!currentSessionId) {
        setSelectedDocumentId(documentId);
        if (documentId) setOntology(await getOntology(documentId));
      }
    });
  }

  useEffect(() => {
    const storedSessions = loadSessions();
    const lastSessionId = window.localStorage.getItem("lastSessionId");
    const lastSession = storedSessions.find((s) => s.id === lastSessionId);
    queueMicrotask(() => {
      if (lastSession) {
        setSessions(storedSessions);
        setCurrentSessionId(lastSession.id);
        setSelectedDocumentId(lastSession.documentId);
        void run("Loading document", async () => {
          setOntology(await getOntology(lastSession.documentId));
        });
      } else {
        const lastDocumentId = window.localStorage.getItem("lastDocumentId");
        if (lastDocumentId) {
          setSelectedDocumentId(lastDocumentId);
          void run("Loading document", async () => {
            setOntology(await getOntology(lastDocumentId));
          });
        }
      }
    });
    void refreshAll(lastSession?.documentId || window.localStorage.getItem("lastDocumentId") || undefined);
    return () => {
      if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleUpload(file: File | undefined) {
    if (!file) return;
    void run("Parsing PDF", async () => {
      const uploaded = await uploadDocument(file);
      setUploadResult(uploaded);
      await refreshAll(uploaded.document.document_id);
      startNewSession(uploaded.document.document_id, file.name);
    });
  }

  function handleSkillUpload(file: File | undefined) {
    if (!file) return;
    void run("Uploading skill", async () => {
      const skill = await uploadSkill(file);
      await refreshAll();
      setSelectedSkillId(skill.skill_id);
      setSkillPreview("");
    });
  }

  function createCyberSkill() {
    void run("Creating cyber skill", async () => {
      const skill = await createSkill(cyberSkillTemplate);
      await refreshAll();
      setSelectedSkillId(skill.skill_id);
      setSkillDrawerOpen(false);
    });
  }

  function createCustomSkill() {
    const sections = skillSections
      .split(/\r?\n/)
      .map((section) => section.trim())
      .filter(Boolean)
      .slice(0, 8);
    if (!sections.length) {
      setError("Add at least one section heading.");
      return;
    }
    void run("Creating skill", async () => {
      const skill = await createSkill({
        name: skillName.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 80) || "custom_skill",
        version: "1.0.0",
        description: "User-created response formatting skill sanitized by the backend schema.",
        output_mode: "markdown",
        required_sections: sections.map((heading) => ({ heading, citation_required: true })),
        tone: "executive",
        citation_style: "page",
        require_citations: true
      });
      await refreshAll();
      setSelectedSkillId(skill.skill_id);
      setSkillDrawerOpen(false);
    });
  }

  function showPreview() {
    if (!selectedSkillId) return;
    void run("Previewing skill", async () => {
      const preview = await previewSkill(selectedSkillId);
      setSkillPreview(preview.formatted_answer);
    });
  }

  function pumpTypewriter() {
    setVisibleAnswer((current) => {
      const next = revealNextCharacter(current, answerBufferRef.current);
      animationRef.current =
        next.length < answerBufferRef.current.length ? requestAnimationFrame(pumpTypewriter) : null;
      return next;
    });
  }

  function appendAnswer(delta: string) {
    answerBufferRef.current += delta;
    if (animationRef.current === null) {
      animationRef.current = requestAnimationFrame(pumpTypewriter);
    }
  }

  function replaceAnswer(answer: string) {
    answerBufferRef.current = answer;
    setVisibleAnswer("");
    if (animationRef.current !== null) cancelAnimationFrame(animationRef.current);
    animationRef.current = requestAnimationFrame(pumpTypewriter);
  }

  function addProgress(step: string) {
    setProgress((current) => (current.includes(step) ? current : [...current, step]));
  }

  function ask(nextMessage = message) {
    const question = nextMessage.trim();
    if (!question) return;
    if (!selectedDocumentId && !isGreeting(question)) {
      setError("Document not selected. Upload or select a PDF before asking document questions.");
      return;
    }
    void run("Answering", async () => {
      setIsAsking(true);
      setCurrentQuestion(question);
      setStreamingRoute("");
      setVisibleAnswer("");
      setStreamCitations([]);
      setProgress([]);
      answerBufferRef.current = "";
      let route = "";
      let traceId = "";
      let graphPaths: string[][] = [];
      let citations: Citation[] = [];
      await sendChatStream(
        {
          document_id: selectedDocumentId || undefined,
          message: question,
          skill_id: selectedSkillId || undefined
        },
        (event) => {
          if (event.event === "route") {
            route = event.data;
            setStreamingRoute(route);
          }
          if (event.event === "progress") addProgress(event.data);
          if (event.event === "citation") {
            const citation = JSON.parse(event.data) as Citation;
            citations = [...citations, citation];
            setStreamCitations(citations);
          }
          if (event.event === "answer_delta") appendAnswer(event.data);
          if (event.event === "answer_replace") replaceAnswer(event.data);
          if (event.event === "error") throw new Error(event.data);
          if (event.event === "trace") traceId = event.data;
        }
      );
      const finalAnswer = answerBufferRef.current;
      setMessage(question);
      if (traceId) {
        window.localStorage.setItem("lastTraceId", traceId);
        const detail = await getTrace(traceId);
        setTrace(detail);
        graphPaths = detail.graph_paths;
        const traceCitations = detail.evidence.map((item) => {
            const evidence = item as { page_number: number; evidence_id: string; text: string };
            return {
              page_number: evidence.page_number,
              evidence_id: evidence.evidence_id,
              text: evidence.text.slice(0, 240)
            };
          });
        citations = traceCitations.length ? traceCitations : citations;
      }
      const newTurn: ChatTurn = {
        question,
        answer: finalAnswer,
        route,
        citations,
        graph_paths: graphPaths,
        trace_id: traceId
      };
      const nextTurns = [...history, newTurn];
      updateCurrentSessionTurns(nextTurns);
      setCurrentQuestion("");
      setVisibleAnswer("");
      setStreamCitations([]);
      setIsAsking(false);
      if (selectedDocumentId) window.localStorage.setItem("lastDocumentId", selectedDocumentId);
    }).finally(() => setIsAsking(false));
  }

  return (
    <main className="chat-shell">
      <aside className="chat-setup">
        <Panel icon={<FileText size={18} />} title="Document">
          <label className="compact-upload">
            <input type="file" accept="application/pdf" onChange={(event) => handleUpload(event.target.files?.[0])} />
            <Upload size={18} />
            Upload PDF
          </label>
          {uploadResult ? (
            <div className="mini-log">
              <span>{uploadResult.parser}</span>
              <strong>{uploadResult.ingestion.page_count} pages</strong>
            </div>
          ) : null}
          <div className="document-list">
            {documents.map((document) => (
              <button
                key={document.document_id}
                className={document.document_id === selectedDocumentId ? "select-row active" : "select-row"}
                onClick={() => {
                  if (document.document_id === selectedDocumentId) return;
                  const existing = sessions.find((s) => s.documentId === document.document_id);
                  if (existing) {
                    loadSession(existing.id);
                  } else {
                    startNewSession(document.document_id, document.filename);
                    void run("Loading document", async () => {
                      setOntology(await getOntology(document.document_id));
                    });
                  }
                  window.localStorage.setItem("lastDocumentId", document.document_id);
                }}
              >
                <span>{document.filename}</span>
                <small>{document.page_count} pages · {document.status}</small>
              </button>
            ))}
          </div>
        </Panel>

        <Panel icon={<ShieldCheck size={18} />} title="Skills">
          <select className="ui-field" value={selectedSkillId} onChange={(event) => setSelectedSkillId(event.target.value)}>
            <option value="">No skill</option>
            {skills.map((skill) => (
              <option key={skill.skill_id} value={skill.skill_id}>
                {skill.definition.name}
              </option>
            ))}
          </select>
          <div className="skill-actions">
            <button className="ui-button" onClick={() => setSkillDrawerOpen(true)}>
              Create skill
            </button>
            <label className="file-link">
              Upload JSON skill
              <input type="file" accept="application/json,.json" onChange={(event) => handleSkillUpload(event.target.files?.[0])} />
            </label>
            <button className="ui-button ghost" disabled={!selectedSkillId} onClick={showPreview}>
              Preview
            </button>
          </div>
          {selectedSkill ? <p className="muted">{selectedSkill.definition.description}</p> : null}
          {skillPreview ? <div className="preview-box"><MarkdownBlock>{skillPreview}</MarkdownBlock></div> : null}
        </Panel>
      </aside>

      <section className="chat-main">
        <header className="chat-header">
          <div className="header-left">
            <button
              className="icon-button hamburger"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open conversation history"
            >
              <Menu size={20} />
            </button>
            <div>
              <p className="eyebrow">Chat workspace</p>
              <h1>{selectedDocument?.filename ?? "Select a PDF"}</h1>
              <p>
                {selectedDocument
                  ? `${selectedDocument.page_count} pages · ${selectedDocument.status}`
                  : "Upload or select a document to start."}
              </p>
            </div>
          </div>
          <div className="status-pill">
            {status === "Ready" ? <Activity size={15} /> : <Loader2 className="spin" size={15} />}
            {status}
          </div>
        </header>

        {error ? (
          <div className="error-box">
            <strong>{error}</strong>
            <button onClick={() => ask()}>Retry</button>
          </div>
        ) : null}

        <div className="prompt-row">
          {prompts.map((prompt) => (
            <button key={prompt} onClick={() => ask(prompt)} disabled={isAsking}>
              {prompt}
            </button>
          ))}
        </div>

        <div className="message-list">
          {history.length === 0 && !currentQuestion ? <EmptyChat /> : null}
          {history.map((chat) => (
            <motion.article key={chat.trace_id || chat.question} className="chat-turn" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
              <div className="user-bubble">{chat.question}</div>
              <div className="assistant-bubble">
                <div className="answer-head">
                  <span>{chat.route || "graph_rag"}</span>
                  <small>{chat.trace_id}</small>
                </div>
                <MarkdownBlock>{chat.answer}</MarkdownBlock>
                <CitationGrid citations={chat.citations} />
              </div>
            </motion.article>
          ))}
          {currentQuestion ? (
            <LiveTurn
              question={currentQuestion}
              answer={visibleAnswer}
              route={streamingRoute}
              progress={progress}
              citations={streamCitations}
            />
          ) : null}
        </div>

        <div className="sticky-composer">
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} disabled={isAsking} />
          <button onClick={() => ask()} disabled={isAsking} aria-label="Ask">
            {isAsking ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
          </button>
        </div>
      </section>

      <aside className="trace-rail">
        <Panel icon={<Activity size={18} />} title="Answer trace">
          {trace ? (
            <div className="score-stack">
              {trace.retrieval.slice(0, 5).map((item, index) => (
                <div key={item.evidence_id} className="score-row">
                  <span>#{index + 1} page {item.page_number}</span>
                  <strong>{item.ranker ?? "local"}</strong>
                  <small>final {formatScore(item.final_score)}</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">Ask a question to populate retrieval scores.</p>
          )}
        </Panel>
        <Panel icon={<FileText size={18} />} title="Ontology">
          {status === "Loading document" && !ontology ? (
            <div className="ontology-loading"><Loader2 className="spin" size={18} /><span>Loading ontology...</span></div>
          ) : ontology ? (
            <div className="ontology-rich">
              <div className="ontology-meta">
                <span>{ontology.object_types.reduce((sum, o) => sum + o.count, 0)} objects</span>
                <span className="ontology-meta-dot">·</span>
                <span>{ontology.relationships.reduce((sum, r) => sum + r.count, 0)} links</span>
              </div>

              <motion.div className="ontology-section" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
                <h3 className="ontology-section-title">Object Types</h3>
                <div className="ontology-objects">
                  {ontology.object_types.map((obj, i) => (
                    <motion.div
                      key={obj.label}
                      className="ontology-object-card"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.06, duration: 0.3 }}
                    >
                      <div className="ontology-object-header">
                        <strong>{obj.label}</strong>
                        <span className="count-badge">{obj.count}</span>
                      </div>
                      {obj.properties.length > 0 && (
                        <div className="ontology-properties">
                          {obj.properties.map((prop) => (
                            <span key={prop} className="ontology-property-tag">{prop}</span>
                          ))}
                        </div>
                      )}
                      {obj.examples.length > 0 && (
                        <div className="ontology-examples">
                          <small>e.g. {obj.examples.slice(0, 2).join(", ")}</small>
                        </div>
                      )}
                    </motion.div>
                  ))}
                </div>
              </motion.div>

              {ontology.relationships.length > 0 && (
                <motion.div className="ontology-section" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25, delay: 0.15 }}>
                  <h3 className="ontology-section-title">Relationships</h3>
                  <div className="ontology-relationships">
                    {ontology.relationships.map((rel, i) => (
                      <motion.div
                        key={`${rel.type}-${rel.source_label}-${rel.target_label}`}
                        className="ontology-relationship-row"
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.15 + i * 0.05, duration: 0.3 }}
                      >
                        <div className="rel-path">
                          <span className="rel-node">{rel.source_label}</span>
                          <svg width="14" height="10" viewBox="0 0 14 10" fill="none" aria-hidden="true">
                            <path d="M1 5h10M9 1l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          <span className="rel-type">{rel.type}</span>
                          <svg width="14" height="10" viewBox="0 0 14 10" fill="none" aria-hidden="true">
                            <path d="M1 5h10M9 1l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          <span className="rel-node">{rel.target_label}</span>
                        </div>
                        {rel.count > 1 && <span className="count-badge">{rel.count}</span>}
                        {rel.examples.length > 0 && (
                          <div className="rel-examples"><small>{rel.examples.slice(0, 1).join(", ")}</small></div>
                        )}
                      </motion.div>
                    ))}
                  </div>
                </motion.div>
              )}
            </div>
          ) : (
            <p className="muted">Ontology loads with the selected document.</p>
          )}
        </Panel>
        <Panel icon={<MessageSquare size={18} />} title="Model">
          {trace?.model_calls?.length ? (
            <div className="metric-grid">
              <div>
                <span>Model</span>
                <strong>{String(trace.model_calls[0].model ?? "n/a")}</strong>
              </div>
              <div>
                <span>Tokens</span>
                <strong>{String(trace.usage?.total_tokens ?? "n/a")}</strong>
              </div>
            </div>
          ) : (
            <p className="muted">Model usage appears after the first answer.</p>
          )}
        </Panel>
        <Panel icon={<ChevronRight size={18} />} title="Graph paths">
          {trace?.graph_paths.length ? (
            <GraphPathView paths={trace.graph_paths} limit={4} />
          ) : (
            <p className="muted">Graph links appear after retrieval.</p>
          )}
        </Panel>
      </aside>

      <AnimatePresence>
        {sidebarOpen ? (
          <motion.div
            className="sidebar-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setSidebarOpen(false)}
          >
            <motion.aside
              className="chat-sidebar"
              initial={{ x: -280 }}
              animate={{ x: 0 }}
              exit={{ x: -280 }}
              transition={{ type: "spring", damping: 25, stiffness: 200 }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="sidebar-top">
                <button
                  className="icon-button"
                  onClick={() => setSidebarOpen(false)}
                  aria-label="Close sidebar"
                >
                  <X size={18} />
                </button>
                <button
                  className="new-conversation-btn"
                  onClick={() => {
                    if (selectedDocumentId) {
                      startNewSession(selectedDocumentId, selectedDocument?.filename || "Unknown");
                    }
                    setSidebarOpen(false);
                  }}
                  disabled={!selectedDocumentId}
                >
                  <PenLine size={16} />
                  New chat
                </button>
              </div>
              <div className="sidebar-divider" />
              <div className="sidebar-history">
                {sessions.length === 0 ? (
                  <p className="muted">No conversations yet</p>
                ) : (
                  sessions.map((session) => {
                    const isActive = session.id === currentSessionId;
                    const preview = session.turns[0]?.question || "New chat";
                    return (
                      <button
                        key={session.id}
                        className={isActive ? "history-row active" : "history-row"}
                        onClick={() => {
                          loadSession(session.id);
                          setSidebarOpen(false);
                        }}
                      >
                        <span>{preview.slice(0, 50)}{preview.length > 50 ? "..." : ""}</span>
                      </button>
                    );
                  })
                )}
              </div>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <AnimatePresence>
        {skillDrawerOpen ? (
          <motion.div className="drawer-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.aside className="skill-drawer" initial={{ x: 420 }} animate={{ x: 0 }} exit={{ x: 420 }}>
              <button className="icon-button" onClick={() => setSkillDrawerOpen(false)} aria-label="Close skill builder">
                <X size={18} />
              </button>
              <p className="eyebrow">Skill builder</p>
              <h2>Create a response format</h2>
              <input className="ui-field" value={skillName} onChange={(event) => setSkillName(event.target.value)} />
              <textarea
                className="ui-field skill-sections"
                value={skillSections}
                onChange={(event) => setSkillSections(event.target.value)}
              />
              <button className="ui-button" onClick={createCustomSkill}>
                Create skill
              </button>
              <button className="ui-button ghost" onClick={createCyberSkill}>
                Use cyber template
              </button>
            </motion.aside>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </main>
  );
}

function LiveTurn({
  question,
  answer,
  route,
  progress,
  citations
}: {
  question: string;
  answer: string;
  route: string;
  progress: string[];
  citations: Citation[];
}) {
  return (
    <motion.article className="chat-turn" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
      <div className="user-bubble">{question}</div>
      <div className="assistant-bubble live">
        <div className="progress-strip">
          {progress.map((step) => (
            <span key={step}>{progressLabels[step] ?? step}</span>
          ))}
        </div>
        <div className="answer-head">
          <span>{route || "streaming"}</span>
          <small>{answer ? "typing" : "working"}</small>
        </div>
        {answer ? <MarkdownBlock>{answer}</MarkdownBlock> : <TypingIndicator />}
        <CitationGrid citations={citations} />
      </div>
    </motion.article>
  );
}

function TypingIndicator() {
  return (
    <div className="typing-indicator" aria-label="Preparing evidence">
      <span />
      <span />
      <span />
    </div>
  );
}

function CitationGrid({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="citation-grid">
      {citations.slice(0, 4).map((citation) => (
        <div key={citation.evidence_id}>
          <strong>p. {citation.page_number}</strong>
          <MarkdownBlock>{citation.text}</MarkdownBlock>
        </div>
      ))}
    </div>
  );
}

function Panel({
  icon,
  title,
  children,
  action
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="workspace-panel">
      <div className="panel-header">
        <h2>{icon}{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function EmptyChat() {
  return (
    <div className="empty-chat">
      <Bot size={34} />
      <h2>Ready for grounded questions.</h2>
      <p>Use a sample prompt or ask against the selected PDF.</p>
    </div>
  );
}

function MarkdownBlock({ children }: { children: string }) {
  return (
    <div className="markdown-body">
      <ReactMarkdown
        rehypePlugins={[rehypeRaw]}
        components={{
          p: ({ children }) => <p className="md-p">{children}</p>,
          li: ({ children }) => <li className="md-li">{children}</li>,
          ul: ({ children }) => <ul className="md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="md-ol">{children}</ol>,
          strong: ({ children }) => <strong className="md-strong">{children}</strong>,
          em: ({ children }) => <em className="md-em">{children}</em>,
          h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
          h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
          h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
          code: ({ children }) => <code className="md-code">{children}</code>,
          pre: ({ children }) => <pre className="md-pre">{children}</pre>
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

function formatScore(value?: number) {
  return typeof value === "number" ? value.toFixed(3) : "n/a";
}

function isGreeting(value: string) {
  return ["hi", "hello", "hey"].includes(value.trim().toLowerCase());
}

function friendlyError(caught: unknown) {
  const message = caught instanceof Error ? caught.message : "Unknown error";
  if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
    return "Backend unavailable. Confirm FastAPI is running on port 8000.";
  }
  if (message.includes("Connection refused") || message.includes("database.connectivity")) {
    return "Cloud SQL proxy unavailable. Start the proxy on port 5432 and retry.";
  }
  if (message.includes("Document not found") || message.includes("404")) {
    return "Document not selected. Choose or upload a PDF and retry.";
  }
  if (message.includes("Answer generation failed")) {
    return "Answer generation failed; fallback used where available.";
  }
  return message.replace(/^\/v1\/[^ ]+ failed with \d+:\s*/, "");
}
