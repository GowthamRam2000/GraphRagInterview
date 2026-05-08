"use client";

import { motion } from "framer-motion";

const nodes = ["PDF", "Parse", "Embed", "Graph", "Rerank", "Answer"];

export function PipelineVisual() {
  return (
    <div className="pipeline-visual" aria-hidden="true">
      <div className="pipeline-grid" />
      {nodes.map((node, index) => (
        <motion.div
          key={node}
          className="pipeline-node"
          style={{
            left: `${8 + index * 14.8}%`,
            top: `${index % 2 === 0 ? 28 : 58}%`
          }}
          initial={{ opacity: 0, y: 18, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ delay: index * 0.12, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
        >
          <span>{node}</span>
        </motion.div>
      ))}
      <motion.div
        className="pipeline-beam"
        initial={{ scaleX: 0, opacity: 0 }}
        animate={{ scaleX: 1, opacity: 1 }}
        transition={{ delay: 0.35, duration: 1.2, ease: "easeOut" }}
      />
      <motion.div
        className="pipeline-pulse"
        animate={{ x: ["0%", "92%"], opacity: [0, 1, 1, 0] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}
