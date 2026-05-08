from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_api_key
from app.services.smoke import run_smoke_checks
from app.services.store import STORE, hydrate_store

router = APIRouter(prefix="/v1/traces", tags=["traces"], dependencies=[Depends(require_api_key)])


@router.get("/ready")
async def traces_ready() -> dict[str, str]:
    return {"status": "traces-api-ready"}


@router.get("")
async def traces_list() -> list[dict]:
    hydrate_store()
    return [
        {
            "trace_id": trace.trace_id,
            "route": trace.route,
            "document_id": trace.document_id,
            "created_at": trace.created_at,
        }
        for trace in STORE.traces.values()
    ]


@router.get("/{trace_id}")
async def traces_get(trace_id: str) -> dict:
    hydrate_store()
    trace = STORE.traces.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {
        "trace_id": trace.trace_id,
        "route": trace.route,
        "user_message": trace.user_message,
        "document_id": trace.document_id,
        "retrieval": trace.retrieval,
        "evidence": trace.evidence,
        "graph_paths": trace.graph_paths,
        "answer": trace.answer,
        "prompts": trace.prompts,
        "model_calls": trace.model_calls,
        "usage": trace.usage,
        "timings": trace.timings,
        "cache": trace.cache,
        "created_at": trace.created_at,
    }


@router.get("/admin/smoke")
async def traces_smoke() -> dict:
    results = await run_smoke_checks()
    return {
        "ok": all(result.ok for result in results),
        "checks": [result.as_dict() for result in results],
    }
