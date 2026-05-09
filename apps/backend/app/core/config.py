from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        extra="ignore",
    )

    app_env: str = "local"
    cors_allowed_origins: str = ""
    store_backend: str = "memory"
    graph_store_backend: str = "memory"
    api_auth_key: str = Field(default="dev-local-auth-key")
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/graphrag"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "password"
    gcs_bucket_raw: str = "raw-pdfs"
    gcs_bucket_artifacts: str = "page-artifacts"
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"
    document_ai_location: str = "us"
    document_ai_processor_id: str = ""
    parser_primary: str = "llamaparse"
    parser_fallback: str = "liteparse"
    llama_cloud_api_key: str = ""
    llamaparse_tier: str = "agentic"
    llamaparse_result_type: str = "markdown"
    liteparse_ocr_enabled: bool = False
    liteparse_dpi: int = 150
    openai_api_key: str = ""
    gemini_api_key: str = ""
    router_model: str = "gpt-5.4-mini"
    extractor_model: str = "gpt-5.4-mini"
    answer_model: str = "gpt-5.4-mini"
    greeting_model: str = "gpt-5.4-mini"
    llm_answer_enabled: bool = True
    router_reasoning_effort: str = "none"
    router_confidence_threshold: float = 0.72
    answer_reasoning_effort: str = "low"
    extractor_reasoning_effort: str = "low"
    prompt_cache_namespace: str = "cognizinterview-graphrag-v1"
    answer_max_output_tokens: int = 900
    embedding_provider: str = "gemini_api"
    embedding_model: str = "gemini-embedding-2"
    embedding_dimension: int = 1536
    embedding_task_type: str = "RETRIEVAL_DOCUMENT"
    rerank_provider: str = "vertex"
    rerank_model: str = "semantic-ranker-default-004"
    rerank_location: str = "global"
    rerank_top_n: int = 8
    rerank_candidate_limit: int = 40


@lru_cache
def get_settings() -> Settings:
    return Settings()
