from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import require_api_key
from app.models.schemas import FinalizeDocumentRequest, UploadUrlRequest
from app.scripts.backfill_multimodal import backfill_documents
from app.services.artifacts import upload_raw_pdf
from app.services.chat import retrieve_evidence_candidates
from app.services.ingestion import (
    create_upload,
    finalize_document,
    finalize_parsed_document,
    get_document_or_none,
    get_ingestion_status,
    get_ontology,
    list_documents,
)
from app.services.parsing import PdfParseError, parse_pdf_bytes

router = APIRouter(
    prefix="/v1/documents",
    tags=["documents"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/ready")
async def documents_ready() -> dict[str, str]:
    return {"status": "documents-api-ready"}


@router.get("")
async def documents_list() -> list[dict]:
    return [document.model_dump() for document in list_documents()]


@router.post("/upload-url")
async def documents_upload_url(request: UploadUrlRequest) -> dict:
    return create_upload(request).model_dump()


@router.post("/upload")
async def documents_upload(
    file: Annotated[UploadFile, File()],
    title: str | None = None,
) -> dict:
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF uploads are supported")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Uploaded PDF is empty")

    upload = create_upload(
        UploadUrlRequest(filename=file.filename or "upload.pdf", content_type="application/pdf")
    )
    raw_artifact = upload_raw_pdf(upload.document_id, file.filename or "upload.pdf", content)
    try:
        parsed = parse_pdf_bytes(content, file.filename or "upload.pdf")
    except PdfParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    status = finalize_parsed_document(
        upload.document_id,
        parsed,
        title=title or file.filename,
        raw_pdf_gcs_uri=raw_artifact.uri,
        legacy_text_only=not raw_artifact.stored,
    )
    if status is None:
        raise HTTPException(status_code=500, detail="Document ingestion failed")
    return {
        "document": upload.model_dump(),
        "ingestion": status.model_dump(),
        "parser": parsed.parser,
        "raw_pdf_gcs_uri": raw_artifact.uri,
        "raw_pdf_stored": raw_artifact.stored,
    }


@router.post("/admin/backfill")
async def documents_admin_backfill(
    document_id: str | None = None,
    all_documents: bool = False,
) -> dict:
    if not all_documents and not document_id:
        raise HTTPException(status_code=422, detail="Pass document_id or all_documents=true")
    results = backfill_documents(None if all_documents else [document_id or ""])
    return {"status": "completed", "results": results}


@router.get("/{document_id}")
async def documents_get(document_id: str) -> dict:
    document = get_document_or_none(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return {
        "document_id": document.document_id,
        "filename": document.filename,
        "title": document.title,
        "status": document.status,
        "page_count": len(document.pages),
        "gcs_uri": document.gcs_uri,
        "raw_pdf_gcs_uri": document.raw_pdf_gcs_uri,
        "artifact_count": len(document.artifact_gcs_uris),
        "legacy_text_only": document.legacy_text_only,
        "parser_metadata": document.parser_metadata,
    }


@router.post("/{document_id}/finalize")
async def documents_finalize(document_id: str, request: FinalizeDocumentRequest) -> dict:
    status = finalize_document(document_id, request)
    if status is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return status.model_dump()


@router.get("/{document_id}/ingestion")
async def documents_ingestion(document_id: str) -> dict:
    status = get_ingestion_status(document_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return status.model_dump()


@router.get("/{document_id}/ontology")
async def documents_ontology(document_id: str) -> dict:
    ontology = get_ontology(document_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return ontology.model_dump()


@router.get("/{document_id}/search-preview")
async def documents_search_preview(document_id: str, q: str, limit: int = 8) -> dict:
    document = get_document_or_none(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    candidates = retrieve_evidence_candidates(document_id, q, max(1, min(limit, 20)))
    return {
        "document_id": document_id,
        "query": q,
        "results": [
            {
                "evidence_id": candidate.evidence.evidence_id,
                "page_number": candidate.evidence.page_number,
                "text": candidate.evidence.text[:500],
                "evidence_type": candidate.evidence.evidence_type,
                "artifact_uri": candidate.evidence.artifact_uri,
                "semantic_score": candidate.semantic_score,
                "lexical_score": candidate.lexical_score,
                "combined_score": candidate.combined_score,
                "rerank_score": candidate.rerank_score,
                "final_score": candidate.final_score,
                "ranker": candidate.ranker,
                "fallback_reason": candidate.fallback_reason,
            }
            for candidate in candidates
        ],
    }


@router.get("/{document_id}/pages/{page_number}")
async def documents_page(document_id: str, page_number: int) -> dict:
    document = get_document_or_none(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    page = document.pages.get(page_number)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return {
        "document_id": document_id,
        "page_number": page.page_number,
        "text": page.text,
        "status": page.status,
        "entity_ids": page.entity_ids,
        "evidence_ids": page.evidence_ids,
        "tables": [
            {
                "table_id": table.table_id,
                "summary": table.summary,
                "artifact_uri": table.artifact_uri,
                "evidence_id": table.evidence_id,
            }
            for table in page.tables
        ],
        "images": [
            {
                "image_id": image.image_id,
                "caption": image.caption,
                "source_ref": image.source_ref,
                "artifact_uri": image.artifact_uri,
                "evidence_id": image.evidence_id,
            }
            for image in page.images
        ],
        "layout_blocks": page.layout_blocks,
        "artifact_uris": page.artifact_uris,
    }
