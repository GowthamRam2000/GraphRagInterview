from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def print_result(name: str, method: str, path: str, status: int, sample: Any) -> None:
    print(f"\n{name}")
    print(f"{method} {path}")
    print(f"status={status}")
    print(json.dumps(sample, indent=2)[:2000])


def expect(status: int, expected: int, label: str) -> None:
    if status != expected:
        raise AssertionError(f"{label} returned {status}, expected {expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--api-key", default="dev-local-auth-key")
    args = parser.parse_args()

    if not args.pdf_path.exists():
        raise FileNotFoundError(args.pdf_path)

    client = TestClient(app)
    headers = {"x-api-key": args.api_key}

    outputs: dict[str, Any] = {}

    response = client.get("/healthz")
    expect(response.status_code, 200, "healthz")
    print_result("Healthz", "GET", "/healthz", response.status_code, response.json())

    ready_paths = [
        ("Chat Ready", "/v1/chat/ready"),
        ("Documents Ready", "/v1/documents/ready"),
        ("Ontology Ready", "/v1/ontology/ready"),
        ("Skills Ready", "/v1/skills/ready"),
        ("Traces Ready", "/v1/traces/ready"),
    ]
    for name, path in ready_paths:
        response = client.get(path, headers=headers)
        expect(response.status_code, 200, name)
        print_result(name, "GET", path, response.status_code, response.json())

    response = client.get("/v1/documents", headers=headers)
    expect(response.status_code, 200, "documents list initial")
    print_result(
        "Documents List Initial",
        "GET",
        "/v1/documents",
        response.status_code,
        response.json(),
    )

    response = client.post(
        "/v1/documents/upload-url",
        headers=headers,
        json={"filename": "manual-finalize.pdf", "content_type": "application/pdf"},
    )
    expect(response.status_code, 200, "documents upload-url")
    upload_url_body = response.json()
    manual_document_id = upload_url_body["document_id"]
    print_result(
        "Documents Upload Url",
        "POST",
        "/v1/documents/upload-url",
        response.status_code,
        upload_url_body,
    )

    response = client.post(
        f"/v1/documents/{manual_document_id}/finalize",
        headers=headers,
        json={
            "title": "Manual Finalize Smoke",
            "pages": [
                "AI Risk Management Framework uses Govern, Map, Measure, and Manage functions.",
                "Risk controls link Accountability, Transparency, Privacy, and Security evidence.",
            ],
        },
    )
    expect(response.status_code, 200, "documents finalize")
    print_result(
        "Documents Finalize",
        "POST",
        f"/v1/documents/{manual_document_id}/finalize",
        response.status_code,
        response.json(),
    )

    with args.pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/v1/documents/upload",
            headers=headers,
            files={"file": (args.pdf_path.name, pdf_file, "application/pdf")},
        )
    expect(response.status_code, 200, "documents upload")
    uploaded = response.json()
    document_id = uploaded["document"]["document_id"]
    outputs["document_id"] = document_id
    outputs["parser"] = uploaded.get("parser")
    print_result("Documents Upload", "POST", "/v1/documents/upload", response.status_code, uploaded)

    document_paths = [
        ("Documents List", "GET", "/v1/documents"),
        ("Documents Get", "GET", f"/v1/documents/{document_id}"),
        ("Documents Ingestion", "GET", f"/v1/documents/{document_id}/ingestion"),
        ("Documents Ontology", "GET", f"/v1/documents/{document_id}/ontology"),
        ("Documents Page", "GET", f"/v1/documents/{document_id}/pages/1"),
        ("Ontology Get", "GET", f"/v1/ontology/{document_id}"),
    ]
    for name, method, path in document_paths:
        response = client.get(path, headers=headers)
        expect(response.status_code, 200, name)
        print_result(name, method, path, response.status_code, response.json())

    response = client.get(
        f"/v1/documents/{document_id}/search-preview",
        headers=headers,
        params={"q": "secure and resilient AI systems", "limit": 5},
    )
    expect(response.status_code, 200, "documents search-preview")
    print_result(
        "Documents Search Preview",
        "GET",
        f"/v1/documents/{document_id}/search-preview",
        response.status_code,
        response.json(),
    )

    response = client.post("/v1/chat", headers=headers, json={"message": "hello"})
    expect(response.status_code, 200, "chat greeting")
    greeting = response.json()
    outputs["greeting_trace_id"] = greeting["trace_id"]
    print_result("Chat Greeting", "POST", "/v1/chat", response.status_code, greeting)

    graph_question = "What are the main functions in the AI Risk Management Framework?"
    response = client.post(
        "/v1/chat",
        headers=headers,
        json={"document_id": document_id, "message": graph_question},
    )
    expect(response.status_code, 200, "chat graph_rag")
    chat = response.json()
    outputs["trace_id"] = chat["trace_id"]
    print_result("Chat Graph RAG", "POST", "/v1/chat", response.status_code, chat)

    response = client.post(
        "/v1/chat/stream",
        headers=headers,
        json={"document_id": document_id, "message": "List ontology domain objects."},
    )
    expect(response.status_code, 200, "chat stream")
    print_result("Chat Stream", "POST", "/v1/chat/stream", response.status_code, response.text)

    response = client.get("/v1/skills", headers=headers)
    expect(response.status_code, 200, "skills list initial")
    print_result("Skills List Initial", "GET", "/v1/skills", response.status_code, response.json())

    skill_payload = {
        "name": "cyber_risk_brief",
        "version": "1.0.0",
        "description": "Cyber risk analyst response format with controls and residual risk.",
        "output_mode": "markdown",
        "required_sections": [
            {"heading": "Cyber Risk Finding", "max_words": 90},
            {"heading": "Relevant Controls", "citation_required": True},
            {"heading": "Residual Risk", "max_words": 70},
        ],
        "tone": "cyber",
        "citation_style": "page",
        "require_citations": True,
    }
    response = client.post("/v1/skills", headers=headers, json=skill_payload)
    expect(response.status_code, 200, "skills create")
    skill = response.json()
    skill_id = skill["skill_id"]
    outputs["skill_id"] = skill_id
    print_result("Skills Create", "POST", "/v1/skills", response.status_code, skill)

    response = client.post(
        "/v1/skills/upload",
        headers=headers,
        files={
            "file": (
                "audit-upload.json",
                json.dumps(
                    {
                        "name": "audit_upload",
                        "version": "1.0.0",
                        "description": "Audit answer format with cited evidence.",
                        "output_mode": "markdown",
                        "required_sections": [
                            {"heading": "Finding", "max_words": 80},
                            {"heading": "Evidence", "citation_required": True},
                        ],
                        "tone": "audit",
                        "citation_style": "page",
                        "require_citations": True,
                    }
                ).encode("utf-8"),
                "application/json",
            )
        },
    )
    expect(response.status_code, 200, "skills upload")
    print_result(
        "Skills Upload",
        "POST",
        "/v1/skills/upload",
        response.status_code,
        response.json(),
    )

    response = client.get("/v1/skills", headers=headers)
    expect(response.status_code, 200, "skills list")
    print_result("Skills List", "GET", "/v1/skills", response.status_code, response.json())

    response = client.post(f"/v1/skills/{skill_id}/preview", headers=headers)
    expect(response.status_code, 200, "skills preview")
    print_result(
        "Skills Preview",
        "POST",
        f"/v1/skills/{skill_id}/preview",
        response.status_code,
        response.json(),
    )

    response = client.post(
        "/v1/chat",
        headers=headers,
        json={
            "document_id": document_id,
            "skill_id": skill_id,
            "message": "Assess security and resilience risks from the AI RMF.",
        },
    )
    expect(response.status_code, 200, "chat with skill")
    print_result("Chat With Skill", "POST", "/v1/chat", response.status_code, response.json())

    response = client.get("/v1/traces", headers=headers)
    expect(response.status_code, 200, "traces list")
    print_result("Traces List", "GET", "/v1/traces", response.status_code, response.json())

    response = client.get(f"/v1/traces/{outputs['trace_id']}", headers=headers)
    expect(response.status_code, 200, "traces get")
    print_result(
        "Traces Get",
        "GET",
        f"/v1/traces/{outputs['trace_id']}",
        response.status_code,
        response.json(),
    )

    response = client.get("/v1/traces/admin/smoke", headers=headers)
    expect(response.status_code, 200, "traces smoke")
    print_result(
        "Traces Smoke",
        "GET",
        "/v1/traces/admin/smoke",
        response.status_code,
        response.json(),
    )

    print("\nSUMMARY")
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
