from app.core.config import Settings


def test_parser_defaults_are_llamaparse_then_liteparse() -> None:
    settings = Settings()
    assert settings.parser_primary == "llamaparse"
    assert settings.parser_fallback == "liteparse"
    assert settings.llamaparse_tier == "agentic"
    assert settings.llamaparse_result_type == "markdown"
    assert settings.liteparse_ocr_enabled is False
    assert settings.liteparse_dpi == 150
    assert settings.embedding_provider == "gemini_api"
    assert settings.embedding_model == "gemini-embedding-2"
    assert settings.embedding_dimension == 1536
    assert settings.embedding_task_type == "RETRIEVAL_DOCUMENT"
    assert settings.rerank_provider == "vertex"
    assert settings.rerank_model == "semantic-ranker-default-004"
    assert settings.rerank_location == "global"
    assert settings.rerank_top_n == 8
    assert settings.rerank_candidate_limit == 40
    assert settings.llm_answer_enabled is True
    assert settings.router_reasoning_effort == "none"
    assert settings.answer_reasoning_effort == "low"
    assert settings.extractor_reasoning_effort == "low"
    assert settings.prompt_cache_namespace == "cognizinterview-graphrag-v1"
