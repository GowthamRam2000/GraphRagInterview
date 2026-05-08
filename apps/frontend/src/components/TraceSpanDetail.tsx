"use client";

import { useState } from "react";
import type { TraceSpan } from "./TraceWaterfall";
import type { TraceDetail } from "@/lib/types";

type Tab = "input" | "output" | "metadata" | "error";

export function TraceSpanDetail({
  span,
  trace,
}: {
  span: TraceSpan;
  trace: TraceDetail;
}) {
  const [tab, setTab] = useState<Tab>(span.status === "error" ? "error" : "output");

  const tabs: { key: Tab; label: string }[] = [
    { key: "output", label: "Output" },
    { key: "input", label: "Input" },
    { key: "metadata", label: "Metadata" },
  ];
  if (span.status === "error") {
    tabs.push({ key: "error", label: "Error" });
  }

  function renderContent() {
    switch (tab) {
      case "input":
        return <CodeBlock data={span.input} />;
      case "output":
        return <CodeBlock data={span.output} />;
      case "metadata":
        return <CodeBlock data={span.metadata} />;
      case "error":
        return <CodeBlock data={span.metadata?.error ?? "No error details"} />;
      default:
        return null;
    }
  }

  return (
    <div className="trace-span-detail">
      <div className="trace-span-detail-header">
        <h4>{span.name}</h4>
        <small>{trace.trace_id}</small>
        <div className="trace-span-detail-tabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              className={tab === t.key ? "active" : ""}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="trace-span-detail-body">{renderContent()}</div>
    </div>
  );
}

function CodeBlock({ data }: { data: unknown }) {
  if (data === undefined || data === null) {
    return <div className="empty-state">No data available</div>;
  }
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return <pre>{text}</pre>;
}
