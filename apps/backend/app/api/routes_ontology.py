from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_api_key
from app.services.ingestion import get_ontology

router = APIRouter(
    prefix="/v1/ontology",
    tags=["ontology"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/ready")
async def ontology_ready() -> dict[str, str]:
    return {"status": "ontology-api-ready"}


@router.get("/{document_id}")
async def ontology_get(document_id: str) -> dict:
    ontology = get_ontology(document_id)
    if ontology is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return ontology.model_dump()
