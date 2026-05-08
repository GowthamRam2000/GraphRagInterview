"use client";

import { Clock, FileText, Route, Layers } from "lucide-react";
import type { TraceDetail } from "@/lib/types";

export function TraceOverview({ trace }: { trace: TraceDetail }) {
  const totalTokens =
    typeof trace.usage?.total_tokens === "number"
      ? trace.usage.total_tokens
      : null;

  const modelName =
    trace.model_calls && trace.model_calls.length > 0 && trace.model_calls[0].model
      ? String(trace.model_calls[0].model)
      : null;

  return (
    <div className="trace-overview">
      <div className="trace-overview-question">
        <h3>{trace.user_message || "No question recorded"}</h3>
        <p>
          {trace.answer
            ? trace.answer.slice(0, 120) +
              (trace.answer.length > 120 ? "..." : "")
            : "Answer pending"}
        </p>
      </div>
      <div className="trace-overview-meta">
        <span className="meta-chip route">
          <Route size={12} />
          {trace.route}
        </span>
        {modelName && (
          <span className="meta-chip">
            <Layers size={12} />
            {modelName}
          </span>
        )}
        {totalTokens !== null && (
          <span className="meta-chip">
            <FileText size={12} />
            {totalTokens.toLocaleString()} tokens
          </span>
        )}
        {trace.timings && (
          <span className="meta-chip">
            <Clock size={12} />
            {formatDuration(trace.timings)}
          </span>
        )}
      </div>
    </div>
  );
}

function formatDuration(timings: Record<string, unknown>): string {
  // Try to compute total from timing entries
  const vals = Object.values(timings).filter(
    (v): v is number => typeof v === "number"
  );
  if (vals.length === 0) return "n/a";
  const total = vals.reduce((a, b) => a + b, 0);
  if (total < 1000) return `${Math.round(total)}ms`;
  return `${(total / 1000).toFixed(2)}s`;
}
