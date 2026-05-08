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
from app.services.store import reset_store


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
    monkeypatch.setenv("DATABASE_URL", database_url)
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
        monkeypatch.delenv("RERANK_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_ANSWER_ENABLED", raising=False)
        get_settings.cache_clear()
