"use client";

import { motion } from "framer-motion";
import { BadgeCheck, BriefcaseBusiness, Code2 } from "lucide-react";

export default function AboutPage() {
  return (
    <main className="about-shell">
      <motion.section
        className="about-hero"
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.55 }}
      >
        <p className="eyebrow">About this build</p>
        <h1>Built by Gowtham Ram M for the Cognizant interview process.</h1>
        <p>
          The project demonstrates a working Graph RAG chatbot with document upload, ontology
          extraction, skill-based response formatting, ranked retrieval, and explainable traces.
        </p>
      </motion.section>

      <section className="about-columns">
        <article>
          <BriefcaseBusiness size={20} />
          <h2>Interview intent</h2>
          <p>
            Show a production-minded demo that a reviewer can operate, inspect, and question
            without reading the code first.
          </p>
        </article>
        <article>
          <Code2 size={20} />
          <h2>Engineering focus</h2>
          <p>
            FastAPI, Pydantic, LlamaParse, Gemini Embedding 2, Vertex reranking, Cloud SQL, Neo4j,
            and a Next.js interface.
          </p>
        </article>
        <article>
          <BadgeCheck size={20} />
          <h2>Demo standard</h2>
          <p>
            The answer path is visible: retrieved pages, graph links, scores, citations, ranker,
            and skill formatting.
          </p>
        </article>
      </section>
    </main>
  );
}
