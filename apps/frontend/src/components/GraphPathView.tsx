"use client";

import { GitBranch } from "lucide-react";

export function GraphPathView({ paths, limit }: { paths: string[][]; limit?: number }) {
  const display = limit ? paths.slice(0, limit) : paths;
  if (!display.length) return null;
  return (
    <div className="graph-path-list">
      {display.map((path, pathIndex) => (
        <div key={`${path.join(":")}-${pathIndex}`} className="graph-path-row">
          <div className="graph-path-nodes">
            {path.map((node, nodeIndex) => (
              <div key={`${node}-${nodeIndex}`} className="graph-path-node">
                <span>{node}</span>
                {nodeIndex < path.length - 1 ? (
                  <svg width="16" height="10" viewBox="0 0 16 10" fill="none" aria-hidden="true">
                    <path d="M1 5h12M10 1l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : null}
              </div>
            ))}
          </div>
          <small className="graph-path-meta">
            <GitBranch size={10} />
            {path.length} nodes
          </small>
        </div>
      ))}
    </div>
  );
}
