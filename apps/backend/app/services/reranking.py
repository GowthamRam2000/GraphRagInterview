from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class RerankInput:
    evidence_id: str
    title: str
    content: str


@dataclass(frozen=True)
class RerankResult:
    evidence_id: str
    score: float


@dataclass(frozen=True)
class RerankOutcome:
    provider: str
    results: list[RerankResult]
    fallback_reason: str | None = None


def rerank_records(query: str, records: list[RerankInput]) -> RerankOutcome:
    settings = get_settings()
    if settings.rerank_provider.lower() != "vertex":
        return RerankOutcome(provider="local", results=[], fallback_reason="reranker disabled")
    if not records:
        return RerankOutcome(provider="local", results=[], fallback_reason="no records")
    if not settings.gcp_project_id:
        return RerankOutcome(provider="local", results=[], fallback_reason="missing GCP_PROJECT_ID")
    try:
        return rerank_with_vertex(query, records, settings)
    except Exception as exc:
        return RerankOutcome(
            provider="local",
            results=[],
            fallback_reason=f"{type(exc).__name__}: {str(exc).splitlines()[0][:180]}",
        )


def rerank_with_vertex(
    query: str,
    records: list[RerankInput],
    settings: Settings,
) -> RerankOutcome:
    token = google_access_token()
    endpoint = (
        "https://discoveryengine.googleapis.com/v1/"
        f"projects/{settings.gcp_project_id}/locations/{settings.rerank_location}/"
        "rankingConfigs/default_ranking_config:rank"
    )
    payload = {
        "model": settings.rerank_model,
        "query": query,
        "topN": min(settings.rerank_top_n, len(records)),
        "ignoreRecordDetailsInResponse": True,
        "records": [
            {"id": record.evidence_id, "title": record.title, "content": record.content[:6000]}
            for record in records[:200]
        ],
    }
    response = httpx.post(
        endpoint,
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
            "x-goog-user-project": settings.gcp_project_id,
        },
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    return RerankOutcome(
        provider="vertex",
        results=[
            RerankResult(evidence_id=str(record["id"]), score=float(record.get("score", 0.0)))
            for record in body.get("records", [])
        ],
    )


def google_access_token() -> str:
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Google ADC did not return an access token")
    return credentials.token
