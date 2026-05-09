from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class SmokeResult:
    name: str
    ok: bool
    detail: str

    def as_dict(self) -> dict[str, str | bool]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


async def run_smoke_checks(settings: Settings | None = None) -> list[SmokeResult]:
    settings = settings or get_settings()
    checks = [
        check_database_url_shape(settings),
        await check_database_connectivity(settings),
        check_gemini_env(settings),
    ]
    checks.extend(
        await asyncio.gather(
            check_gcs(settings),
            check_neo4j(settings),
            check_openai(settings),
            check_llamacloud(settings),
            check_gemini_embedding(settings),
            check_vertex_reranker(settings),
        )
    )
    return checks


def check_database_url_shape(settings: Settings) -> SmokeResult:
    try:
        url = make_url(settings.database_url)
        return SmokeResult(
            name="database_url.parse",
            ok=True,
            detail=f"driver={url.drivername}, database={url.database or 'missing'}",
        )
    except Exception as exc:
        return SmokeResult(name="database_url.parse", ok=False, detail=safe_detail(exc))


async def check_database_connectivity(settings: Settings) -> SmokeResult:
    if "/cloudsql/" in settings.database_url:
        return SmokeResult(
            name="database.connectivity",
            ok=True,
            detail=(
                "Cloud SQL socket URL configured; live connection requires "
                "Cloud Run or Cloud SQL proxy"
            ),
        )
    try:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        try:
            async with engine.connect() as connection:
                value = (await connection.execute(text("select 1"))).scalar_one()
            return SmokeResult(
                name="database.connectivity",
                ok=value == 1,
                detail="select 1 succeeded",
            )
        finally:
            await engine.dispose()
    except Exception as exc:
        return SmokeResult(name="database.connectivity", ok=False, detail=safe_detail(exc))


def check_gemini_env(settings: Settings) -> SmokeResult:
    return SmokeResult(
        name="gemini.env",
        ok=bool(settings.gemini_api_key and settings.embedding_model),
        detail=f"provider={settings.embedding_provider}, model={settings.embedding_model}",
    )


async def check_gcs(settings: Settings) -> SmokeResult:
    try:
        from google.cloud import storage

        client = storage.Client(project=settings.gcp_project_id or None)
        raw = client.get_bucket(settings.gcs_bucket_raw)
        artifacts = client.get_bucket(settings.gcs_bucket_artifacts)
        return SmokeResult(
            name="gcs.buckets",
            ok=True,
            detail=f"raw={raw.name}, artifacts={artifacts.name}",
        )
    except Exception as exc:
        return SmokeResult(name="gcs.buckets", ok=False, detail=safe_detail(exc))


async def check_neo4j(settings: Settings) -> SmokeResult:
    if settings.graph_store_backend.lower() != "neo4j":
        return SmokeResult(
            name="neo4j",
            ok=True,
            detail=f"skipped; GRAPH_STORE_BACKEND={settings.graph_store_backend}",
        )
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            connection_timeout=10,
        )
        try:
            driver.verify_connectivity()
            with driver.session() as session:
                value = session.run("RETURN 1 AS ok").single()["ok"]
            return SmokeResult(name="neo4j", ok=value == 1, detail="RETURN 1 succeeded")
        finally:
            driver.close()
    except Exception as exc:
        return SmokeResult(name="neo4j", ok=False, detail=safe_detail(exc))


async def check_openai(settings: Settings) -> SmokeResult:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=15)
        model = client.models.retrieve(settings.router_model)
        return SmokeResult(name="openai.model", ok=True, detail=f"model={model.id}")
    except Exception as exc:
        return SmokeResult(name="openai.model", ok=False, detail=safe_detail(exc))


async def check_llamacloud(settings: Settings) -> SmokeResult:
    try:
        from llama_cloud import LlamaCloud

        client = LlamaCloud(api_key=settings.llama_cloud_api_key, timeout=15)
        projects = client.projects.list()
        count = len(getattr(projects, "items", projects if isinstance(projects, list) else []))
        return SmokeResult(name="llamacloud.projects", ok=True, detail=f"count={count}")
    except Exception as exc:
        return SmokeResult(name="llamacloud.projects", ok=False, detail=safe_detail(exc))


async def check_gemini_embedding(settings: Settings) -> SmokeResult:
    try:
        from google import genai
        from google.genai.types import EmbedContentConfig

        client = genai.Client(api_key=settings.gemini_api_key)
        response = client.models.embed_content(
            model=settings.embedding_model,
            contents=["graph rag smoke test"],
            config=EmbedContentConfig(
                task_type=settings.embedding_task_type,
                output_dimensionality=settings.embedding_dimension,
            ),
        )
        dimension = len(response.embeddings[0].values)
        return SmokeResult(
            name="gemini.embedding",
            ok=dimension == settings.embedding_dimension,
            detail=f"dimension={dimension}",
        )
    except Exception as exc:
        return SmokeResult(name="gemini.embedding", ok=False, detail=safe_detail(exc))


async def check_vertex_reranker(settings: Settings) -> SmokeResult:
    if settings.rerank_provider.lower() != "vertex":
        return SmokeResult(
            name="vertex.reranker",
            ok=True,
            detail=f"provider={settings.rerank_provider}",
        )
    try:
        from app.services.reranking import RerankInput, rerank_records

        outcome = await asyncio.to_thread(
            rerank_records,
            "secure and resilient AI systems",
            [
                RerankInput(
                    evidence_id="secure",
                    title="Security",
                    content=(
                        "AI systems are secure and resilient when they preserve "
                        "confidentiality, integrity, availability, and degrade safely."
                    ),
                ),
                RerankInput(
                    evidence_id="other",
                    title="Governance",
                    content="Governance defines review cadence and accountability.",
                ),
            ],
        )
        if outcome.provider != "vertex" or not outcome.results:
            return SmokeResult(
                name="vertex.reranker",
                ok=False,
                detail=outcome.fallback_reason or "reranker returned no results",
            )
        top = outcome.results[0]
        return SmokeResult(
            name="vertex.reranker",
            ok=top.evidence_id == "secure",
            detail=f"model={settings.rerank_model}, top={top.evidence_id}, score={top.score}",
        )
    except Exception as exc:
        return SmokeResult(name="vertex.reranker", ok=False, detail=safe_detail(exc))


def safe_detail(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:220]}"
