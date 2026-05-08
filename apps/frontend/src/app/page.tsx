"use client";

import { motion } from "framer-motion";
import { ArrowRight, Database, GitBranch, Layers3, SearchCheck } from "lucide-react";
import Link from "next/link";

import { PipelineVisual } from "@/components/PipelineVisual";

const stages = [
  ["Parse", "LlamaParse Agentic converts long PDFs into page-level evidence."],
  ["Embed", "Gemini Embedding 2 vectors each evidence span for semantic recall."],
  ["Connect", "Cloud SQL stores state while Neo4j carries entities and relationships."],
  ["Rerank", "Hybrid semantic/BM25 candidates are reranked by Vertex semantic ranker."],
  ["Trace", "Every answer exposes route, scores, citations, and graph paths."]
];

export default function Home() {
  return (
    <main>
      <section className="hero-shell">
        <PipelineVisual />
        <motion.div
          className="hero-copy"
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <p className="eyebrow">Graph RAG interview demo</p>
          <h1>CognizInterview Document Intelligence</h1>
          <p className="hero-lede">
            Upload a PDF, build a traceable graph, and ask grounded questions with ranked evidence.
          </p>
          <div className="hero-actions">
            <Link className="action-primary" href="/chat">
              Open chat <ArrowRight size={17} />
            </Link>
            <Link className="action-secondary" href="/trace">
              Inspect traces
            </Link>
          </div>
        </motion.div>
      </section>

      <section className="section-band">
        <div className="section-heading">
          <p className="eyebrow">How it works</p>
          <h2>From uploaded PDF to explainable answer.</h2>
        </div>
        <div className="stage-rail">
          {stages.map(([title, body], index) => (
            <motion.article
              key={title}
              className="stage-item"
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ delay: index * 0.07, duration: 0.45 }}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{body}</p>
            </motion.article>
          ))}
        </div>
      </section>

      <section className="proof-band">
        <div>
          <Layers3 size={24} />
          <h2>Built for reviewers and builders.</h2>
        </div>
        <div className="proof-grid">
          <Proof icon={<Database size={18} />} title="Persistent" text="Cloud SQL and Neo4j back the demo flow." />
          <Proof icon={<SearchCheck size={18} />} title="Ranked" text="Semantic, lexical, and Vertex scores are visible." />
          <Proof icon={<GitBranch size={18} />} title="Traceable" text="Each answer links back to pages and graph paths." />
        </div>
      </section>
    </main>
  );
}

function Proof({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <article className="proof-item">
      {icon}
      <h3>{title}</h3>
      <p>{text}</p>
    </article>
  );
}
