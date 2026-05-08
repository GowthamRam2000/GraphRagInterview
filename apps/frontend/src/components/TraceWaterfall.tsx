"use client";

import { motion } from "framer-motion";

export interface TraceSpan {
  id: string;
  name: string;
  type: "retrieval" | "reranking" | "generation" | "graph_query" | "skill_format" | "other";
  parent_id?: string;
  start_time: number;
  end_time: number;
  duration_ms: number;
  status: "success" | "error" | "in_progress";
  input?: string | Record<string, unknown>;
  output?: string | Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

interface TraceWaterfallProps {
  spans: TraceSpan[];
  totalDuration: number;
  onSelectSpan: (span: TraceSpan) => void;
  selectedSpanId?: string;
}

export function TraceWaterfall({ spans, totalDuration, onSelectSpan, selectedSpanId }: TraceWaterfallProps) {
  if (!spans.length) {
    return (
      <div className="trace-waterfall">
        <div className="empty-state">No execution spans recorded for this trace.</div>
      </div>
    );
  }

  const spanMap = new Map(spans.map((s) => [s.id, s]));

  function getDepth(span: TraceSpan): number {
    let depth = 0;
    let current = span;
    while (current.parent_id && spanMap.has(current.parent_id)) {
      depth++;
      current = spanMap.get(current.parent_id)!;
    }
    return depth;
  }

  return (
    <div className="trace-waterfall">
      <div className="trace-waterfall-header">
        <span>Operation</span>
        <span>Timeline</span>
        <span style={{ textAlign: "right" }}>Duration</span>
      </div>
      {spans.map((span, index) => {
        const depth = getDepth(span);
        const offsetPercent = totalDuration > 0 ? (span.start_time / totalDuration) * 100 : 0;
        const widthPercent = totalDuration > 0 ? (span.duration_ms / totalDuration) * 100 : 0;
        const isSelected = span.id === selectedSpanId;
        return (
          <motion.div
            key={span.id}
            className={`trace-span-row ${isSelected ? "selected" : ""}`}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.04, duration: 0.25 }}
            onClick={() => onSelectSpan(span)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectSpan(span);
              }
            }}
          >
            <div className="trace-span-name">
              {Array.from({ length: depth }).map((_, i) => (
                <span key={i} className="indent" />
              ))}
              <span className={`type-dot ${span.status === "error" ? "error" : span.type}`} />
              <span>{span.name}</span>
            </div>
            <div className="trace-span-bar-track">
              <div
                className={`trace-span-bar ${span.status === "error" ? "error" : span.type}`}
                style={{
                  left: `${offsetPercent}%`,
                  width: `${Math.max(widthPercent, 1)}%`,
                }}
                title={`${span.name}: ${span.duration_ms}ms`}
              />
            </div>
            <div className="trace-span-duration">{span.duration_ms}ms</div>
          </motion.div>
        );
      })}
    </div>
  );
}
