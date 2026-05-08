from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import require_api_key
from app.models.schemas import FinalizeDocumentRequest, UploadUrlRequest
from app.services.chat import retrieve_evidence_candidates
from app.services.ingestion import (
    create_upload,
    finalize_document,
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

    try:
        parsed = parse_pdf_bytes(content, file.filename or "upload.pdf")
    except PdfParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    upload = create_upload(
        UploadUrlRequest(filename=file.filename or "upload.pdf", content_type="application/pdf")
    )
    status = finalize_document(
        upload.document_id,
        FinalizeDocumentRequest(
            title=title or file.filename,
            pages=[page.text for page in parsed.pages],
        ),
    )
    if status is None:
        raise HTTPException(status_code=500, detail="Document ingestion failed")
    return {
        "document": upload.model_dump(),
        "ingestion": status.model_dump(),
        "parser": parsed.parser,
    }


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
    }
