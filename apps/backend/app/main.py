from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_chat, routes_documents, routes_ontology, routes_skills, routes_traces
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(title="CognizInterview Graph RAG API", version="0.1.0")
    local_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    cloud_origins = [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=local_origins if settings.app_env == "local" else cloud_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_chat.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_ontology.router)
    app.include_router(routes_skills.router)
    app.include_router(routes_traces.router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
