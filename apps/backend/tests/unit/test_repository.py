from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.models.schemas import (
    ChatRequest,
    FinalizeDocumentRequest,
    SkillDefinition,
    SkillSection,
    UploadUrlRequest,
)
from app.services.chat import answer_chat
from app.services.ingestion import create_upload, finalize_document, list_documents
from app.services.repository import (
    PersistentRepository,
    set_repository_for_tests,
    to_sync_database_url,
)
from app.services.skills import create_skill, list_skills
from app.services.store import (
    STORE,
    DocumentRecord,
    EvidenceRecord,
    ImageRecord,
    PageRecord,
    TableRecord,
    document_from_payload,
    document_to_payload,
    graph_payload_for_document,
    load_graph_payload,
    reset_store,
)


def test_database_url_is_converted_to_sync_driver() -> None:
    async_url = "postgresql+asyncpg://user:pass@localhost:5432/graphrag"

    assert (
        to_sync_database_url(async_url)
        == "postgresql+psycopg://user:pass@localhost:5432/graphrag"
    )


def test_sql_repository_persists_documents_skills_and_traces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'graphrag.db'}"
    repository = PersistentRepository(database_url)
    repository.clear_all()

    monkeypatch.setenv("STORE_BACKEND", "sql")
    monkeypatch.setenv("GRAPH_STORE_BACKEND", "sql")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("GCP_PROJECT_ID", "")
    monkeypatch.setenv("GCS_BUCKET_ARTIFACTS", "")
    monkeypatch.setenv("GCS_BUCKET_RAW", "")
    monkeypatch.setenv("RERANK_PROVIDER", "local")
    monkeypatch.setenv("LLM_ANSWER_ENABLED", "false")
    get_settings.cache_clear()
    set_repository_for_tests(repository)
    reset_store()

    try:
        upload = create_upload(
            UploadUrlRequest(filename="durability.pdf", content_type="application/pdf")
        )
        finalize_document(
            upload.document_id,
            FinalizeDocumentRequest(
                title="Durability Test",
                pages=["Cloud Run uses Cloud SQL persistence for Graph RAG traces."],
            ),
        )
        skill = create_skill(
            SkillDefinition(
                name="audit",
                version="1.0.0",
                description="Show evidence in audit format.",
                output_mode="markdown",
                required_sections=[
                    SkillSection(heading="Answer"),
                    SkillSection(heading="Evidence", citation_required=True),
                ],
            )
        )
        chat = answer_chat(
            ChatRequest(
                document_id=upload.document_id,
                message="What uses Cloud SQL persistence?",
                skill_id=skill.skill_id,
            )
        )
        assert chat is not None

        reset_store()

        documents = list_documents()
        skills = list_skills()
        assert [document.document_id for document in documents] == [upload.document_id]
        assert [record.skill_id for record in skills] == [skill.skill_id]

        snapshot = repository.load_snapshot()
        assert upload.document_id in snapshot["documents"]
        assert upload.document_id in snapshot["graphs"]
        assert skill.skill_id in snapshot["skills"]
        assert chat.trace_id in snapshot["traces"]
    finally:
        set_repository_for_tests(None)
        reset_store()
        monkeypatch.delenv("STORE_BACKEND", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        monkeypatch.delenv("GCS_BUCKET_ARTIFACTS", raising=False)
        monkeypatch.delenv("GCS_BUCKET_RAW", raising=False)
        monkeypatch.delenv("RERANK_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_ANSWER_ENABLED", raising=False)
        get_settings.cache_clear()


def test_document_payload_round_trips_multimodal_graph_fields() -> None:
    reset_store()
    document = DocumentRecord(
        document_id="doc_mm",
        title="Multimodal PDF",
        filename="multimodal.pdf",
        status="completed",
        raw_pdf_gcs_uri="gs://raw/doc_mm/multimodal.pdf",
        artifact_gcs_uris=["gs://artifacts/doc_mm/pages/1/page.md"],
        parser_metadata={"parser": "llamaparse", "tier": "agentic"},
        legacy_text_only=False,
    )
    document.pages = {
        1: PageRecord(
            page_number=1,
            text="Figure 1 describes AI lifecycle risk.",
            tables=[
                TableRecord(
                    table_id="table_1",
                    page_number=1,
                    markdown="| Stage | Risk |",
                    summary="Lifecycle table",
                    artifact_uri="gs://artifacts/doc_mm/pages/1/tables/table_1.json",
                )
            ],
            images=[
                ImageRecord(
                    image_id="image_1",
                    page_number=1,
                    caption="AI lifecycle figure",
                    artifact_uri="gs://artifacts/doc_mm/pages/1/images/image_1.json",
                )
            ],
            layout_blocks=[{"type": "figure"}],
            artifact_uris={"markdown": "gs://artifacts/doc_mm/pages/1/page.md"},
        )
    }
    STORE.documents[document.document_id] = document
    STORE.evidence["ev_image_1"] = EvidenceRecord(
        evidence_id="ev_image_1",
        document_id="doc_mm",
        page_number=1,
        text="AI lifecycle figure",
        entities=[],
        evidence_type="image",
        artifact_uri="gs://artifacts/doc_mm/pages/1/images/image_1.json",
        content_summary="Figure evidence",
        embedding=[0.1, 0.2],
        metadata={"image_id": "image_1"},
    )

    restored = document_from_payload(document_to_payload(document))
    graph_payload = graph_payload_for_document(document.document_id)
    reset_store()
    load_graph_payload(graph_payload)

    assert restored.raw_pdf_gcs_uri == "gs://raw/doc_mm/multimodal.pdf"
    assert restored.artifact_gcs_uris == ["gs://artifacts/doc_mm/pages/1/page.md"]
    assert restored.pages[1].tables[0].summary == "Lifecycle table"
    assert restored.pages[1].images[0].caption == "AI lifecycle figure"
    assert restored.pages[1].layout_blocks == [{"type": "figure"}]
    assert STORE.evidence["ev_image_1"].evidence_type == "image"
    assert STORE.evidence["ev_image_1"].artifact_uri.endswith("image_1.json")
    reset_store()
