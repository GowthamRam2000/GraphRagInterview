from types import SimpleNamespace
from unittest.mock import patch

from app.core.config import get_settings
from app.rag.answerer import stream_answer_with_llm
from app.rag.prompts import build_answer_prompt
from app.services.store import EvidenceRecord


def test_openai_streaming_deltas_are_combined_and_usage_is_recorded(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ANSWER_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()
    prompt = build_answer_prompt(
        message="What is governed?",
        evidence=[
            EvidenceRecord(
                evidence_id="ev_1",
                document_id="doc_1",
                page_number=1,
                text="Governance evidence.",
                entities=["Governance"],
            )
        ],
        graph_paths=[],
    )
    completed = SimpleNamespace(
        id="resp_1",
        output_text="Governance evidence. [p. 1]",
        usage=SimpleNamespace(
            input_tokens=12,
            output_tokens=5,
            total_tokens=17,
            input_tokens_details=SimpleNamespace(cached_tokens=3),
        ),
    )
    stream = [
        SimpleNamespace(type="response.output_text.delta", delta="Governance "),
        SimpleNamespace(type="response.output_text.delta", delta="evidence. [p. 1]"),
        SimpleNamespace(type="response.completed", response=completed),
    ]
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_kwargs: stream)
    )

    with patch("app.rag.answerer.OpenAI", return_value=fake_client):
        events = list(stream_answer_with_llm(prompt, "fallback"))

    assert [event.delta for event in events if event.kind == "delta"] == [
        "Governance ",
        "evidence. [p. 1]",
    ]
    final = events[-1].result
    assert final is not None
    assert final.answer == "Governance evidence. [p. 1]"
    assert final.model_call["status"] == "ok"
    assert final.usage["total_tokens"] == 17
    assert final.cache["cached_input_tokens"] == 3
    get_settings.cache_clear()
