import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { ChatWorkspace } from "./ChatWorkspace";

vi.mock("@/lib/api", () => ({
  cyberSkillTemplate: {
    name: "cyber_risk_brief",
    version: "1.0.0",
    description: "Cyber format",
    output_mode: "markdown",
    required_sections: [{ heading: "Finding" }],
    tone: "cyber",
    citation_style: "page",
    require_citations: true
  },
  listDocuments: vi.fn(async () => [
    {
      document_id: "doc_1",
      filename: "NIST.AI.100-1.pdf",
      title: "NIST",
      status: "completed",
      page_count: 48
    }
  ]),
  listSkills: vi.fn(async () => []),
  getOntology: vi.fn(async () => ({
    document_id: "doc_1",
    object_types: [],
    relationships: []
  })),
  getTrace: vi.fn(async () => ({
    trace_id: "trace_1",
    route: "graph_rag",
    document_id: "doc_1",
    created_at: 1,
    user_message: "Question",
    retrieval: [],
    evidence: [],
    graph_paths: [],
    answer: "Govern Map",
    usage: { total_tokens: 10 },
    model_calls: [{ model: "gpt-5.4-mini" }]
  })),
  sendChatStream: vi.fn(
    async (
      _input: { document_id?: string; message: string; skill_id?: string },
      onEvent: (event: { event: string; data: string }) => void
    ) => {
      onEvent({ event: "route", data: "graph_rag" });
      onEvent({ event: "progress", data: "retrieving" });
      await new Promise((resolve) => setTimeout(resolve, 20));
      onEvent({
        event: "citation",
        data: JSON.stringify({ page_number: 25, evidence_id: "ev_1", text: "Core functions" })
      });
      onEvent({ event: "answer_delta", data: "Govern" });
      onEvent({ event: "answer_delta", data: " Map" });
      onEvent({ event: "trace", data: "trace_1" });
      onEvent({ event: "done", data: "ok" });
    }
  ),
  uploadDocument: vi.fn(),
  uploadSkill: vi.fn(),
  createSkill: vi.fn(),
  previewSkill: vi.fn()
}));

describe("ChatWorkspace", () => {
  it("renders chat-first controls and streams an answer", async () => {
    render(<ChatWorkspace />);

    expect((await screen.findAllByText("NIST.AI.100-1.pdf")).length).toBeGreaterThan(0);
    expect(screen.getByText("Upload PDF")).toBeInTheDocument();
    expect(screen.getByText("Create skill")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "What are the four core functions in the AI Risk Management Framework?" }
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Retrieving evidence")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Govern Map/)).toBeInTheDocument());
    expect(screen.getByText("p. 25")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled();
  });
});
